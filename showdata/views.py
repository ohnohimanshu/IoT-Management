import logging
import json
import concurrent.futures
from functools import lru_cache

# Try to import ujson for faster parsing, fall back to standard json if not available
try:
    import ujson
    use_ujson = True
except ImportError:
    import json as ujson  # Use standard json module as fallback
    use_ujson = False
    logging.info("ujson module not found, using standard json module instead")
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from pymongo import MongoClient
from pymongo.read_preferences import ReadPreference
from api.serializers import DeviceDataSerializer
from devices.models import Device
from api.models import DeviceData
from datetime import timedelta
import time

logger = logging.getLogger(__name__)

# Performance tuning settings
MAX_DATA_POINTS = 15000  # Increased for high-resolution data
CACHE_TTL = 300  # Increased cache time to 5 minutes
BATCH_SIZE_MIN = 100  # Minimum batch size for parallel processing
THREAD_COUNT = min(8, (settings.THREAD_COUNT if hasattr(settings, 'THREAD_COUNT') else 4))  # Configurable thread count

# Connection pool settings - optimized values
MONGO_MAX_POOL_SIZE = 150  # Increased for higher concurrency
MONGO_MIN_POOL_SIZE = 20   # Increase minimum connections
MONGO_MAX_IDLE_TIME_MS = 60000  # Longer idle time to reuse connections
MONGO_CONNECT_TIMEOUT_MS = 2000
MONGO_SOCKET_TIMEOUT_MS = 5000

# Cache keys
def _device_cache_key(device_id, time_range):
    return f"device_data:{device_id}:{time_range}"

# MongoDB connection singleton with connection pooling
_mongo_client = None
def get_mongo_client():
    global _mongo_client
    if _mongo_client is None:
        uri = getattr(settings, 'MONGO_URI', None)
        if not uri:
            logger.error('MONGO_URI not set in settings')
            return None
            
        # Configure connection pool for optimal performance
        _mongo_client = MongoClient(
            uri,
            maxPoolSize=MONGO_MAX_POOL_SIZE,
            minPoolSize=MONGO_MIN_POOL_SIZE, 
            maxIdleTimeMS=MONGO_MAX_IDLE_TIME_MS,
            connectTimeoutMS=MONGO_CONNECT_TIMEOUT_MS,
            socketTimeoutMS=MONGO_SOCKET_TIMEOUT_MS,
            retryWrites=True,
            appName='HighPerformanceDeviceAPI',
            compressors='zlib',  # Enable network compression
            waitQueueTimeoutMS=2000  # Prevent hanging on connection queue
        )
    return _mongo_client

# Use functools.lru_cache for in-memory caching of collection
@lru_cache(maxsize=32)  # Reduced to optimize memory usage
def get_mongo_collection():
    """Get MongoDB collection with caching"""
    client = get_mongo_client()
    if not client:
        return None
    
    db_name = getattr(settings, 'MONGO_DB_NAME', None)
    if not db_name:
        logger.error('MONGO_DB_NAME not set in settings')
        return None
        
    db = client[db_name]
    # Use read preference for optimized reads
    return db.get_collection(
        DeviceData._meta.db_table,
        read_preference=ReadPreference.NEAREST
    )

@lru_cache(maxsize=64)  # Reduced cache size for time filters
def get_time_filter(time_range):
    """Return cutoff datetime for a given time range with caching"""
    if not time_range:
        return None  # Return None to show all data by default
        
    if 'latest' in time_range.lower():
        return None

    # Pre-compute now once
    now = timezone.now()
    
    # Use a dictionary for direct lookups instead of multiple comparisons
    mapping = {
        '10_latest': 10,
        '1_hour': timedelta(hours=1),
        '1_hour'.lower(): timedelta(hours=1),
        '6_hour': timedelta(hours=6),
        '12_hour': timedelta(hours=12),
        '1_day': timedelta(days=1),
        '1_week': timedelta(weeks=1),
        '2_weeks': timedelta(weeks=2),
        '1_month': timedelta(days=30),
        '3_months': timedelta(days=90),
        '6_months': timedelta(days=180),
        '1_year': timedelta(days=365),
        '5_years': timedelta(days=1825),
        'all': None
    }
    
    # Optimize lookup
    delta = mapping.get(time_range) or mapping.get(time_range.lower())
    return now - delta if isinstance(delta, timedelta) else None

def calculate_optimal_interval(time_range, since, max_points=MAX_DATA_POINTS):
    """Calculate optimal time interval based on time range"""
    now = timezone.now()
    if not since:
        # Default to 1 day if no time range specified
        total_seconds = 24 * 60 * 60
    else:
        total_seconds = (now - since).total_seconds()
    
    # Ensure we don't exceed max points and have reasonable intervals
    interval = max(int(total_seconds * 1000 / max_points), 1)
    
    # Round interval to a reasonable value for better caching
    if interval < 1000:  # Less than 1 second
        return interval  # Keep as is for high-frequency data
    elif interval < 60000:  # Less than 1 minute
        return round(interval / 1000) * 1000  # Round to nearest second
    else:
        return round(interval / 60000) * 60000  # Round to nearest minute
    
def aggregate_data_with_mongodb(device, since, time_range, max_points=MAX_DATA_POINTS):
    """
    High-performance data aggregation with MongoDB using optimal interval calculation
    and advanced aggregation pipeline.
    """
    start_time = time.time()
    
    # Check cache first
    cache_key = _device_cache_key(device.id, time_range)
    cached_result = cache.get(cache_key)
    if cached_result:
        logger.debug(f"Cache hit for {cache_key}, returning {len(cached_result)} records")
        return cached_result
    
    # Fast path for latest entries
    if time_range and 'latest' in time_range.lower():
        limit = int(time_range.lower().split('_')[-1]) if '_' in time_range else 10
        collection = get_mongo_collection()
        if collection:
            try:
                # Use projection to limit fields returned
                raw_data = list(collection.find(
                    {'device': device.id},
                    {'_id': 0, 'timestamp': 1, 'data': 1}
                ).sort('timestamp', -1).limit(limit))
                
                # Reverse to get ascending order
                raw_data.reverse()
                
                results = []
                for doc in raw_data:
                    results.append(DeviceData(device=device, timestamp=doc['timestamp'], data=doc['data']))
                
                logger.debug(f"Latest data retrieval took {time.time() - start_time:.4f}s")
                
                # Cache the results
                cache.set(cache_key, results, CACHE_TTL)
                return results
            except Exception as e:
                logger.error(f'MongoDB latest data retrieval failed: {e}')
        
        # Fallback to ORM
        qs = DeviceData.objects.filter(device=device).order_by('-timestamp')[:limit]
        result = list(reversed(qs))
        cache.set(cache_key, result, CACHE_TTL)
        return result

    # For 'all' time range, don't use aggregation
    if time_range == 'all':
        collection = get_mongo_collection()
        if collection:
            try:
                raw_data = list(collection.find(
                    {'device': device.id},
                    {'_id': 0, 'timestamp': 1, 'data': 1}
                ).sort('timestamp', 1))
                
                results = []
                for doc in raw_data:
                    results.append(DeviceData(device=device, timestamp=doc['timestamp'], data=doc['data']))
                
                logger.debug(f"All data retrieval took {time.time() - start_time:.4f}s for {len(results)} records")
                cache.set(cache_key, results, CACHE_TTL)
                return results
            except Exception as e:
                logger.error(f'MongoDB all data retrieval failed: {e}')
        
        # Fallback to ORM for all data
        result = list(DeviceData.objects.filter(device=device).order_by('timestamp'))
        cache.set(cache_key, result, CACHE_TTL)
        return result

    # Calculate optimal interval based on time range
    interval = calculate_optimal_interval(time_range, since, max_points)
    
    # Build aggregation pipeline with smoothing
    match_stage = {'device': device.device_id}
    if since:
        match_stage['timestamp'] = {'$gte': since}
    
    # Optimized pipeline - using $match earlier and optimizing $group
    pipeline = [
        {'$match': match_stage},
        {'$sort': {'timestamp': 1}},
        {'$group': {
            '_id': {'$subtract': [
                {'$toLong': '$timestamp'}, 
                {'$mod': [{'$toLong': '$timestamp'}, interval]}
            ]},
            'timestamp': {'$first': '$timestamp'},
            'data': {'$first': '$data'},
            'count': {'$sum': 1}
        }},
        {'$sort': {'_id': 1}},
        {'$project': {
            '_id': 0,
            'timestamp': 1,
            'data': 1,
            'count': 1
        }}
    ]

    collection = get_mongo_collection()
    if collection:
        try:
            # Add index hint if available
            options = {'allowDiskUse': True}
            
            # Execute the aggregation
            raw = list(collection.aggregate(pipeline, **options))
            logger.debug(f"MongoDB aggregation took {time.time() - start_time:.4f}s for {len(raw)} data points")
            
            # Build DeviceData instances with smoothed data
            results = []
            for doc in raw:
                # Apply smoothing if we have enough data points
                if doc.get('count', 0) > 1:
                    data = doc['data']
                    # Round numeric values for cleaner display
                    for key, value in data.items():
                        if isinstance(value, (int, float)):
                            data[key] = round(value, 2)
                results.append(DeviceData(device=device, timestamp=doc['timestamp'], data=doc['data']))
            
            # Cache the results
            cache.set(cache_key, results, CACHE_TTL)
            return results
        except Exception as e:
            logger.error(f'MongoDB aggregation failed: {e}')

    # Fallback to optimized ORM query
    orm_qs = DeviceData.objects.filter(device=device)
    if since:
        orm_qs = orm_qs.filter(timestamp__gte=since)
    
    # Use iterator() to avoid loading everything into memory at once
    result = list(orm_qs.order_by('timestamp'))
    cache.set(cache_key, result, CACHE_TTL)
    return result

def process_data_batch(data_objs, start_idx, end_idx):
    """Process a batch of data objects in parallel with smoothing"""
    results = []
    for rd in data_objs[start_idx:end_idx]:
        try:
            # Use ujson for faster parsing
            parsed = ujson.loads(rd.data) if isinstance(rd.data, str) else rd.data
            
            # Ensure numeric values are properly formatted
            for key, value in parsed.items():
                if isinstance(value, (int, float)):
                    # Round to 2 decimal places for cleaner display
                    parsed[key] = round(value, 2)
            
            results.append({
                'timestamp': rd.timestamp.isoformat(),
                'data': parsed
            })
        except Exception as e:
            logger.error(f"Error processing data point: {str(e)}")
            continue
    return results

@login_required
def get_sensor_data(request, device_id):
    try:
        device = get_object_or_404(Device, device_id=device_id)
        time_range = request.GET.get('timeRange', '10_latest')  # Changed default to 10_latest
        
        # Get all data first
        device_data = DeviceData.objects.filter(device=device)
        
        # Only apply time filter if not 'all'
        if time_range != 'all':
            since = get_time_filter(time_range)
            if since:
                device_data = device_data.filter(timestamp__gte=since)
        
        # Order by timestamp
        device_data = device_data.order_by('timestamp')
        
        # Format data
        formatted_data = []
        for entry in device_data:
            try:
                data_dict = entry.data if isinstance(entry.data, dict) else json.loads(entry.data)
                data_dict['timestamp'] = entry.timestamp.isoformat()
                formatted_data.append(data_dict)
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON for entry {entry.id}")
                continue
        
        return JsonResponse({
            'status': device.status,
            'data': formatted_data,
            'total_records': len(formatted_data)
        })
        
    except Exception as e:
        logger.error(f"Error in get_sensor_data: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fetch_device_data(request, device_id):
    """API endpoint for programmatic access"""
    return _handle_sensor_request(request, device_id, Response)

def stream_device_data(request, device_id):
    """Stream large datasets as JSON chunks"""
    try:
        device = get_object_or_404(Device, id=device_id)
        if not (device.user == request.user or request.user.is_staff):
            return JsonResponse({'error': 'Access denied'}, status=403)

        time_range = request.GET.get('timeRange', request.GET.get('time_range', '1_day'))
        since = get_time_filter(time_range)
        chunk_size = int(request.GET.get('chunk_size', 1000))  # Allow configurable chunk size
        
        def generate_json_chunks():
            yield '{"device_name": "%s", "device_status": "%s", "data": [' % (
                device.device_name, device.device_status)
            
            # Use a cursor instead of loading all data at once
            collection = get_mongo_collection()
            if collection:
                match_stage = {'device': device.device_id}
                if since:
                    match_stage['timestamp'] = {'$gte': since}
                
                # Use batch size for efficient streaming
                cursor = collection.find(
                    match_stage, 
                    {'_id': 0, 'timestamp': 1, 'data': 1}
                ).sort('timestamp', 1).batch_size(chunk_size)
                
                first = True
                for doc in cursor:
                    if not first:
                        yield ','
                    else:
                        first = False
                    
                    # Use ujson for faster serialization
                    parsed = ujson.loads(doc['data']) if isinstance(doc['data'], str) else doc['data']
                    item = {'timestamp': doc['timestamp'].isoformat(), 'data': parsed}
                    yield ujson.dumps(item)
                
                cursor.close()
            
            yield ']}'
        
        return StreamingHttpResponse(
            generate_json_chunks(),
            content_type='application/json'
        )
    except Exception as e:
        logger.error(f"Error streaming device data: {e}")
        return JsonResponse({'error': 'Internal server error', 'details': str(e)}, status=500)

def _handle_sensor_request(request, device_id, responder):
    """
    Shared logic for both JSON views and DRF endpoint with optimized performance
    """
    try:
        start_time = time.time()
        
        # Use request caching for repeated requests
        request_cache_key = f"device_request:{device_id}:{request.GET.urlencode()}"
        cached_response = cache.get(request_cache_key)
        if cached_response and not request.GET.get('no_cache'):
            logger.debug(f"Request cache hit for {request_cache_key}")
            if responder is JsonResponse:
                return JsonResponse(cached_response)
            else:
                return Response(cached_response)
        
        # Optimize access check
        device = get_object_or_404(Device, device_id=device_id) if responder is Response else get_object_or_404(Device, id=device_id)
        if responder is JsonResponse and not (device.user == request.user or request.user.is_staff):
            return JsonResponse({'error': 'Access denied'}, status=403)

        # Get parameters
        time_range = request.GET.get('timeRange', request.GET.get('time_range', '1_day'))
        since = get_time_filter(time_range)
        
        # Check for large data request - stream very large datasets
        if time_range and ('5_years' in time_range or 'all' in time_range) and not request.GET.get('no_stream'):
            return stream_device_data(request, device_id)
        
        # Use more aggressive data point limit for extremely large time ranges to prevent OOM
        max_points = MAX_DATA_POINTS
        if time_range and ('3_months' in time_range or '6_months' in time_range):
            max_points = int(MAX_DATA_POINTS * 0.75)  # 75% of max points
        elif time_range and ('1_year' in time_range or '5_years' in time_range or 'all' in time_range):
            max_points = int(MAX_DATA_POINTS * 0.5)   # 50% of max points
        
        # Regular processing
        data_objs = aggregate_data_with_mongodb(device, since, time_range, max_points)
        
        # Process data in parallel for large datasets
        data_count = len(data_objs)
        
        # Calculate optimal batch size and thread count based on data size
        thread_count = min(THREAD_COUNT, max(1, data_count // 500))
        batch_size = max(data_count // thread_count, BATCH_SIZE_MIN)
        
        if data_count > 1000:
            # Use parallel processing for large datasets
            payload = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
                future_to_batch = {
                    executor.submit(process_data_batch, data_objs, i, min(i + batch_size, data_count)): i
                    for i in range(0, data_count, batch_size)
                }
                for future in concurrent.futures.as_completed(future_to_batch):
                    payload.extend(future.result())
        else:
            # Process normally for smaller datasets
            payload = []
            for rd in data_objs:
                parsed = ujson.loads(rd.data) if isinstance(rd.data, str) else rd.data
                payload.append({'timestamp': rd.timestamp.isoformat(), 'data': parsed})

        processing_time = time.time() - start_time
        response_data = {
            'device_name': device.device_name,
            'device_status': device.device_status,
            'data': payload,
            'data_count': len(payload),
            'processing_time_ms': int(processing_time * 1000)
        }
        
        # Cache response for frequently accessed data
        cache_ttl = min(CACHE_TTL, 60) if processing_time > 0.5 else CACHE_TTL  # Shorter cache for slow queries
        cache.set(request_cache_key, response_data, cache_ttl)
        
        logger.debug(f"Request processed in {processing_time:.4f}s with {thread_count} threads")
        
        if responder is JsonResponse:
            return JsonResponse(response_data)
        else:
            return Response(response_data)

    except Device.DoesNotExist:
        return responder({'error': 'Device not found'}, status=404)
    except Exception as e:
        logger.error(f"Error retrieving device data: {e}", exc_info=True)
        return responder(
            {'error': 'Internal server error', 'details': str(e)},
            status=500 if responder is JsonResponse else status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ---- HTML Show Data Views moved from devices app ----
@login_required
def device_data_view(request, device_id):
    logger.info(f"Starting device_data_view for device_id: {device_id}")
    try:
        try:
            device = get_object_or_404(Device, device_id=device_id)
            logger.info(f"Found device: {device.device_name}")
        except Exception as e:
            logger.error(f"Error getting device: {str(e)}")
            return render(request, 'device_data.html', {
                'error': 'Device not found or error accessing device data.'
            })

        time_range = request.GET.get('timeRange', '10_latest')
        try:
            page = int(request.GET.get('page', 1))
        except ValueError:
            page = 1
        rows_per_page = 10

        logger.info(f"Fetching data with time_range: {time_range}, page: {page}")

        try:
            device_data = DeviceData.objects.filter(device=device).order_by('-timestamp')
            total_count = device_data.count()
            logger.info(f"Found {total_count} total records")

            if total_count == 0:
                logger.warning("No data found for device")
                return render(request, 'device_data.html', {
                    'device': device,
                    'time_range': time_range,
                    'error': 'No data available for this device.'
                })
        except Exception as e:
            logger.error(f"Error querying device data: {str(e)}")
            return render(request, 'device_data.html', {
                'device': device,
                'time_range': time_range,
                'error': 'Error retrieving device data.'
            })

        if time_range == '10_latest':
            try:
                latest_data = list(device_data[:10])
                if not latest_data:
                    logger.warning("No latest data found")
                    return render(request, 'device_data.html', {
                        'device': device,
                        'time_range': time_range,
                        'error': 'No latest data available.'
                    })

                formatted_data = []
                for entry in latest_data:
                    try:
                        if hasattr(entry.data, 'items'):
                            data_dict = dict(entry.data)
                        else:
                            try:
                                data_dict = json.loads(str(entry.data))
                            except json.JSONDecodeError:
                                data_dict = {'raw_data': str(entry.data)}

                        data_dict['timestamp'] = entry.timestamp.isoformat()
                        formatted_data.append(data_dict)
                    except Exception as e:
                        logger.error(f"Error formatting entry {entry.id}: {str(e)}")
                        continue

                if not formatted_data:
                    logger.warning("No valid formatted data available")
                    return render(request, 'device_data.html', {
                        'device': device,
                        'time_range': time_range,
                        'error': 'No valid data available for display.'
                    })

                plot_data_formatted = {}
                try:
                    all_keys = set()
                    for entry in formatted_data:
                        all_keys.update(k for k in entry.keys() if k not in ['device_id', 'status', 'timestamp'])

                    for key in all_keys:
                        plot_data_formatted[key] = {'timestamps': [], 'values': []}

                    for entry in formatted_data:
                        timestamp = entry['timestamp']
                        for key in all_keys:
                            if key in entry and entry[key] is not None:
                                try:
                                    value = float(entry[key])
                                    plot_data_formatted[key]['timestamps'].append(timestamp)
                                    plot_data_formatted[key]['values'].append(value)
                                except (ValueError, TypeError):
                                    continue
                except Exception as e:
                    logger.error(f"Error preparing plot data: {str(e)}")
                    plot_data_formatted = {}

                return render(request, 'device_data.html', {
                    'device': device,
                    'time_range': time_range,
                    'data': formatted_data,
                    'plot_data': json.dumps(plot_data_formatted),
                    'current_page': 1,
                    'total_pages': 1,
                    'has_next': False,
                    'has_previous': False,
                    'total_rows': len(formatted_data)
                })

            except Exception as e:
                logger.error(f"Error processing latest data: {str(e)}")
                return render(request, 'device_data.html', {
                    'device': device,
                    'time_range': time_range,
                    'error': 'Error processing latest data.'
                })
        else:
            try:
                now = timezone.now()
                start_time = None

                if time_range == '1_hour':
                    start_time = now - timedelta(hours=1)
                elif time_range == '6_hour':
                    start_time = now - timedelta(hours=6)
                elif time_range == '12_hour':
                    start_time = now - timedelta(hours=12)
                elif time_range == '1_day':
                    start_time = now - timedelta(days=1)
                elif time_range == '1_week':
                    start_time = now - timedelta(weeks=1)
                elif time_range == '2_weeks':
                    start_time = now - timedelta(weeks=2)
                elif time_range == '1_month':
                    start_time = now - timedelta(days=30)
                elif time_range == '3_months':
                    start_time = now - timedelta(days=90)
                elif time_range == '6_months':
                    start_time = now - timedelta(days=180)
                elif time_range == '1_year':
                    start_time = now - timedelta(days=365)
                elif time_range == '5_years':
                    start_time = now - timedelta(days=1825)

                if start_time:
                    device_data = device_data.filter(timestamp__gte=start_time)
                    logger.info(f"Filtered data to {device_data.count()} records after time filter")

                total_rows = device_data.count()
                total_pages = (total_rows + rows_per_page - 1) // rows_per_page if total_rows > 0 else 1

                page = max(1, min(page, total_pages))

                start_idx = (page - 1) * rows_per_page
                end_idx = start_idx + rows_per_page
                paginated_data = list(device_data[start_idx:end_idx])

                logger.info(f"Paginated data: {len(paginated_data)} records for page {page} of {total_pages}")

                if not paginated_data:
                    logger.warning("No data found for the selected criteria")
                    return render(request, 'device_data.html', {
                        'device': device,
                        'time_range': time_range,
                        'error': 'No data available for the selected time range or page.'
                    })

                formatted_data = []
                for entry in paginated_data:
                    try:
                        if hasattr(entry.data, 'items'):
                            data_dict = dict(entry.data)
                        else:
                            try:
                                data_dict = json.loads(str(entry.data))
                            except json.JSONDecodeError:
                                data_dict = {'raw_data': str(entry.data)}

                        data_dict['timestamp'] = entry.timestamp.isoformat()
                        formatted_data.append(data_dict)
                    except Exception as e:
                        logger.error(f"Error formatting entry {entry.id}: {str(e)}")
                        continue

                if not formatted_data:
                    logger.warning("No valid formatted data available")
                    return render(request, 'device_data.html', {
                        'device': device,
                        'time_range': time_range,
                        'error': 'No valid data available for display.'
                    })

                plot_data_formatted = {}
                try:
                    chart_data = list(device_data.order_by('timestamp'))
                    logger.info(f"Preparing chart data with {len(chart_data)} points")

                    all_keys = set()
                    for entry in chart_data:
                        try:
                            if hasattr(entry.data, 'items'):
                                data_dict = dict(entry.data)
                            else:
                                try:
                                    data_dict = json.loads(str(entry.data))
                                except json.JSONDecodeError:
                                    continue
                            all_keys.update(k for k in data_dict.keys() if k not in ['device_id', 'status', 'timestamp'])
                        except Exception as e:
                            logger.error(f"Error processing chart data entry: {str(e)}")
                            continue

                    for key in all_keys:
                        plot_data_formatted[key] = {'timestamps': [], 'values': []}

                    for entry in chart_data:
                        try:
                            if hasattr(entry.data, 'items'):
                                data_dict = dict(entry.data)
                            else:
                                try:
                                    data_dict = json.loads(str(entry.data))
                                except json.JSONDecodeError:
                                    continue

                            ist_timestamp = entry.timestamp + timedelta(hours=5, minutes=30)
                            timestamp = ist_timestamp.isoformat()

                            for key in all_keys:
                                if key in data_dict and data_dict[key] is not None:
                                    try:
                                        value = float(data_dict[key])
                                        plot_data_formatted[key]['timestamps'].append(timestamp)
                                        plot_data_formatted[key]['values'].append(value)
                                    except (ValueError, TypeError):
                                        continue
                        except Exception as e:
                            logger.error(f"Error processing chart data point: {str(e)}")
                            continue

                    logger.info(f"Successfully prepared chart data with {len(all_keys)} data series")
                except Exception as e:
                    logger.error(f"Error preparing chart data: {str(e)}")
                    plot_data_formatted = {}

                return render(request, 'device_data.html', {
                    'device': device,
                    'time_range': time_range,
                    'data': formatted_data,
                    'plot_data': json.dumps(plot_data_formatted),
                    'current_page': page,
                    'total_pages': total_pages,
                    'has_next': page < total_pages,
                    'has_previous': page > 1,
                    'total_rows': total_rows
                })

            except Exception as e:
                logger.error(f"Error processing time range data: {str(e)}", exc_info=True)
                return render(request, 'device_data.html', {
                    'device': device,
                    'time_range': time_range,
                    'error': 'Error processing data for the selected time range.'
                })

    except Exception as e:
        logger.error(f"Error in device_data_view: {str(e)}", exc_info=True)
        return render(request, 'device_data.html', {
            'device': device if 'device' in locals() else None,
            'time_range': time_range if 'time_range' in locals() else '10_latest',
            'error': 'An error occurred while processing your request. Please try again later.'
        })


@login_required
def device_data_api(request, device_id):
    try:
        device = Device.objects.get(device_id=device_id, user=request.user)
        end_time = timezone.now()
        start_time = end_time - timedelta(hours=24)

        data_points = DeviceData.objects.filter(
            device=device,
            timestamp__range=(start_time, end_time)
        ).order_by('timestamp')

        data = {
            'labels': [point.timestamp.strftime('%Y-%m-%d %H:%M:%S') for point in data_points],
            'values': [getattr(point, 'value', None) for point in data_points]
        }

        return JsonResponse({'success': True, 'data': data})
    except Device.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Device not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
