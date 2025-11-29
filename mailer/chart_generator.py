import logging
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
from io import BytesIO
from typing import Optional, Tuple, Dict, Any
from collections import Counter
from django.utils import timezone
from datetime import datetime, timedelta
import traceback

logger = logging.getLogger(__name__)

def generate_charts(device_name: str, past_24hrs_data: list) -> Tuple[Optional[BytesIO], Optional[BytesIO], Optional[Dict[str, Any]]]:
    """
    Generate professional-grade charts for device metrics and status using Plotly.
    Dynamically handles different sensor types per device.
    
    Args:
        device_name (str): Name or identifier of the device
        past_24hrs_data (list): List of device data entries for the past 24 hours
    
    Returns:
        tuple: (metrics_buffer, status_buffer, status_report)
            - metrics_buffer: Buffer containing metrics chart
            - status_buffer: Buffer containing status chart
            - status_report: Dictionary containing status change details
    """
    logger.info(f"Generating charts for device: {device_name}")
    
    if not past_24hrs_data:
        logger.warning(f"No data available for device {device_name} for chart generation")
        return None, None, None
    
    try:
        # Convert data to pandas DataFrame for easier manipulation
        df = pd.DataFrame([
            {
                'timestamp': entry.timestamp,
                **entry.data # Include all data keys dynamically
            }
            for entry in past_24hrs_data
        ])
        
        # Sort by timestamp
        df = df.sort_values('timestamp')
        
        # Discover all numeric sensor keys dynamically (excluding 'status')
        all_data_keys = set()
        for entry in past_24hrs_data:
            all_data_keys.update(entry.data.keys())
        
        # Filter out non-sensor keys and find numeric sensors
        excluded_keys = {'status', 'device_id', 'id', 'created_at', 'updated_at'}
        potential_sensor_keys = [key for key in all_data_keys if key not in excluded_keys]
        
        # Test which keys have numeric data
        numeric_sensor_keys = []
        for key in potential_sensor_keys:
            has_numeric_data = False
            for entry in past_24hrs_data:
                value = entry.data.get(key)
                if value is not None:
                    try:
                        float(value)
                        has_numeric_data = True
                        break
                    except (ValueError, TypeError):
                        continue
            if has_numeric_data:
                numeric_sensor_keys.append(key)
        
        logger.info(f"Found {len(numeric_sensor_keys)} numeric sensor types for {device_name}: {numeric_sensor_keys}")
        
        # --- Generate Dynamic Device Metrics Chart ---
        metrics_buffer = None
        
        if numeric_sensor_keys:
            # Define color palette for different sensors
            colors = [
                '#EF553B',  # Red
                '#00CC96',  # Green
                '#636EFA',  # Blue
                '#FF6692',  # Pink
                '#B6E880',  # Light Green
                '#FF97FF',  # Magenta
                '#FECB52',  # Orange
                '#FFA15A',  # Light Orange
                '#19D3F3',  # Cyan
                '#AB63FA',  # Purple
            ]
            
            # Create dynamic sensor plot configurations
            sensor_plot_configs = {}
            for i, key in enumerate(numeric_sensor_keys):
                # Create readable names and units
                readable_name = key.replace('_', ' ').title()
                
                # Try to determine units based on key name
                units = ""
                key_lower = key.lower()
                if 'temp' in key_lower:
                    units = " (°C)"
                elif 'humid' in key_lower:
                    units = " (%)"
                elif 'signal' in key_lower or 'rssi' in key_lower:
                    units = " (dBm)"
                elif 'voltage' in key_lower or 'volt' in key_lower:
                    units = " (V)"
                elif 'current' in key_lower:
                    units = " (A)"
                elif 'pressure' in key_lower:
                    units = " (Pa)"
                elif 'light' in key_lower or 'lux' in key_lower:
                    units = " (lx)"
                elif 'ph' in key_lower:
                    units = " (pH)"
                
                sensor_plot_configs[key] = {
                    'name': readable_name,
                    'color': colors[i % len(colors)],
                    'title': f"{readable_name}{units}"
                }
            
            # Create subplots - one row for each sensor metric
            fig_metrics = make_subplots(
                rows=len(sensor_plot_configs), cols=1,
                shared_xaxes=True,
                vertical_spacing=0.08,
                subplot_titles=tuple(config['title'] for config in sensor_plot_configs.values())
            )

            row_num = 1
            plottable_sensor_data_found = False
            
            for key, config in sensor_plot_configs.items():
                if key in df.columns:
                    numeric_values = []
                    timestamps = []
                    
                    for index, row in df.iterrows():
                        value = row.get(key)
                        if value is not None:
                            try:
                                numeric_value = float(value)
                                numeric_values.append(numeric_value)
                                timestamps.append(row['timestamp'])
                            except (ValueError, TypeError):
                                logger.warning(f"Skipping non-numeric value for key '{key}' on device {device_name}: {value}")
                                pass
                    
                    if numeric_values:
                        # Create fill color with transparency
                        fill_color = config['color']
                        if fill_color.startswith('#'):
                            # Convert hex to rgba
                            hex_color = fill_color.lstrip('#')
                            rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
                            fill_color = f'rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, 0.1)'
                        
                        fig_metrics.add_trace(
                            go.Scatter(
                                x=timestamps,
                                y=numeric_values,
                                mode='lines+markers',
                                name=config['name'],
                                line=dict(color=config['color'], width=2),
                                marker=dict(size=4),
                                fill='tozeroy',
                                fillcolor=fill_color,
                                showlegend=False
                            ),
                            row=row_num, col=1
                        )
                        plottable_sensor_data_found = True
                    else:
                        logger.warning(f"No plottable numeric data found for key '{key}' on device {device_name}")

                row_num += 1

            if plottable_sensor_data_found:
                # Customize metrics chart layout
                fig_metrics.update_layout(
                    title=dict(
                        text=f"Device Metrics: {device_name}",
                        font=dict(size=18, color='#2c3e50'),
                        x=0.5
                    ),
                    plot_bgcolor='white',
                    paper_bgcolor='white',
                    showlegend=False,
                    height=max(300, 150 * len(sensor_plot_configs)),
                    width=1000,
                    hovermode='x unified',
                    margin=dict(l=80, r=80, t=80, b=80)
                )
                
                # Update all x-axes and y-axes
                for i in range(len(sensor_plot_configs)):
                    axis_num = i + 1
                    fig_metrics.update_xaxes(
                        title='Time' if i == len(sensor_plot_configs) - 1 else '',
                        tickformat='%m/%d %H:%M',
                        gridcolor='lightgray',
                        gridwidth=1,
                        row=axis_num, col=1
                    )
                    fig_metrics.update_yaxes(
                        gridcolor='lightgray',
                        gridwidth=1,
                        row=axis_num, col=1
                    )
                
                # Save metrics chart to buffer
                metrics_buffer = BytesIO()
                try:
                    fig_metrics.write_image(metrics_buffer, format='png', engine='kaleido')
                    metrics_buffer.seek(0)
                except Exception as e:
                    logger.error(f"Error saving metrics chart to buffer for {device_name}: {str(e)}")
                    metrics_buffer = None
            else:
                logger.warning(f"No plottable sensor data found for metrics chart for device {device_name}")

        # --- Generate Detailed Status Report Data ---
        status_report_data = None
        # Re-calculate status_report_data as it's needed for timeline data
        if 'status' in df.columns and not df.empty:
            status_changes_for_log = []
            current_status = None
            # Ensure data is sorted by timestamp before processing changes
            df_sorted = df.sort_values('timestamp').reset_index(drop=True)

            for index, row in df_sorted.iterrows():
                row_status = str(row['status']).strip().lower()  # Normalize: lowercase
                
                # Normalize status values: ON -> active, OFF -> inactive
                if row_status.upper() == 'ON' or row_status in ['active', 'online']:
                    normalized_status = 'active'
                elif row_status.upper() == 'OFF' or row_status in ['inactive', 'offline']:
                    normalized_status = 'inactive'
                else:
                    normalized_status = row_status
                
                # Only track actual changes (not redundant same-status entries)
                if current_status is None or normalized_status != current_status:
                    status_changes_for_log.append({
                        'timestamp': row['timestamp'],
                        'status': normalized_status,
                        'is_initial': current_status is None
                    })
                    current_status = normalized_status

            detailed_status_report_periods = []
            total_active_time = 0
            total_inactive_time = 0

            # Calculate periods and durations
            for i in range(len(status_changes_for_log)):
                start_change = status_changes_for_log[i]
                start_time = start_change['timestamp']
                current_status = start_change['status']  # Already normalized and lowercase
                
                # Determine end time
                if i + 1 < len(status_changes_for_log):
                    end_time = status_changes_for_log[i+1]['timestamp']
                elif not df_sorted.empty:
                    end_time = df_sorted.iloc[-1]['timestamp']
                else:
                    end_time = timezone.now()

                # Ensure start time is before end time
                if start_time >= end_time:
                    continue

                duration = (end_time - start_time).total_seconds() / 60  # Duration in minutes

                previous_status = status_changes_for_log[i-1]['status'] if i > 0 else "N/A"

                detailed_status_report_periods.append({
                    'start_time': start_time,
                    'end_time': end_time,
                    'from_status': previous_status,
                    'to_status': current_status,
                    'duration': duration
                })

                # Accumulate total active/inactive time
                if current_status == 'active':
                    total_active_time += duration
                else:
                    total_inactive_time += duration

            # Calculate active percentage based on the data duration, not necessarily 24 hours if data is less
            data_time_span_seconds = (df_sorted.iloc[-1]['timestamp'] - df_sorted.iloc[0]['timestamp']).total_seconds() if len(df_sorted) > 1 else 0
            actual_active_time_seconds = total_active_time * 60
            active_percentage = round((actual_active_time_seconds / data_time_span_seconds * 100), 1) if data_time_span_seconds > 0 else 0

            status_report_data = {
                'total_changes': len([c for c in status_changes_for_log if not c.get('is_initial')]),
                'total_active_time': round(total_active_time, 2),
                'total_inactive_time': round(total_inactive_time, 2),
                'active_percentage': active_percentage,
                'detailed_periods': detailed_status_report_periods,
                'changes': status_changes_for_log  # Include for email compatibility
            }
        else:
             status_report_data = {
                'total_changes': 0,
                'total_active_time': 0,
                'total_inactive_time': 0,
                'active_percentage': 0,
                'detailed_periods': [],
                'changes': []
            }
        
        
        # --- Generate Enhanced Status Timeline Chart ---
        status_buffer = None
        
        if 'status' in df.columns and not df.empty:
            
            # Use detailed_status_report_periods calculated earlier
            detailed_periods = status_report_data.get('detailed_periods', [])
            
            if detailed_periods:
                # Helper function to format duration in human-readable format
                def format_duration(minutes):
                    """Convert minutes to human-readable format"""
                    if minutes < 1:
                        return f"{int(minutes * 60)}s"
                    elif minutes < 60:
                        return f"{int(minutes)}m"
                    else:
                        hours = int(minutes // 60)
                        mins = int(minutes % 60)
                        if mins > 0:
                            return f"{hours}h {mins}m"
                        return f"{hours}h"
                
                # Create subplots: Timeline (top) and Summary (bottom)
                fig_status = make_subplots(
                    rows=2, cols=1,
                    row_heights=[0.65, 0.35],
                    subplot_titles=(
                        f'{device_name} - Status Timeline (Last 24 Hours)',
                        'Active vs Inactive Time'
                    ),
                    vertical_spacing=0.15,
                    specs=[[{"type": "scatter"}], [{"type": "bar"}]]
                )
                
                # Color mapping
                color_map = {
                    'active': '#2ecc71',    # Green
                    'online': '#2ecc71',    # Green
                    'inactive': '#e74c3c',  # Red
                    'offline': '#e74c3c'    # Red
                }
                
                # --- Top Panel: Detailed Timeline ---
                # Create timeline bars for each period
                for i, period in enumerate(detailed_periods):
                    status = period['to_status'].lower()
                    start = period['start_time']
                    end = period['end_time']
                    duration = period['duration']
                    
                    color = color_map.get(status, '#95a5a6')  # Default gray
                    
                    # Add horizontal bar for this period
                    fig_status.add_trace(
                        go.Scatter(
                            x=[start, end, end, start, start],
                            y=[0.3, 0.3, 0.7, 0.7, 0.3],
                            fill='toself',
                            fillcolor=color,
                            line=dict(color=color, width=2),
                            mode='lines',
                            name=status.capitalize(),
                            showlegend=(i == 0 or (i > 0 and detailed_periods[i-1]['to_status'].lower() != status)),
                            hovertemplate=(
                                f'<b>Status:</b> {status.capitalize()}<br>'
                                f'<b>Start:</b> {start.strftime("%m/%d %H:%M")}<br>'
                                f'<b>End:</b> {end.strftime("%m/%d %H:%M")}<br>'
                                f'<b>Duration:</b> {format_duration(duration)}<br>'
                                '<extra></extra>'
                            ),
                            legendgroup=status
                        ),
                        row=1, col=1
                    )
                    
                    # Add duration label in the middle of each period
                    mid_time = start + (end - start) / 2
                    duration_text = format_duration(duration)
                    
                    # Only show label if period is wide enough (> 30 minutes)
                    if duration > 30:
                        fig_status.add_annotation(
                            x=mid_time,
                            y=0.5,
                            text=duration_text,
                            showarrow=False,
                            font=dict(size=10, color='white', family='Arial Black'),
                            row=1, col=1
                        )
                    
                    # Add transition markers (vertical lines at status changes)
                    if i > 0:
                        prev_status = detailed_periods[i-1]['to_status'].lower()
                        if prev_status != status:
                            # Add vertical line at transition
                            fig_status.add_trace(
                                go.Scatter(
                                    x=[start, start],
                                    y=[0.2, 0.8],
                                    mode='lines',
                                    line=dict(color='#34495e', width=2, dash='dot'),
                                    showlegend=False,
                                    hovertemplate=(
                                        f'<b>Transition:</b> {prev_status.capitalize()} → {status.capitalize()}<br>'
                                        f'<b>Time:</b> {start.strftime("%m/%d %H:%M:%S")}<br>'
                                        '<extra></extra>'
                                    )
                                ),
                                row=1, col=1
                            )
                
                # Update timeline panel layout
                fig_status.update_xaxes(
                    title='Time',
                    tickformat='%m/%d %H:%M',
                    gridcolor='#ecf0f1',
                    gridwidth=1,
                    showgrid=True,
                    row=1, col=1
                )
                fig_status.update_yaxes(
                    title='',
                    showticklabels=False,
                    range=[0, 1],
                    showgrid=False,
                    row=1, col=1
                )
                
                # --- Bottom Panel: Summary Bar Chart ---
                total_active = status_report_data.get('total_active_time', 0)
                total_inactive = status_report_data.get('total_inactive_time', 0)
                active_pct = status_report_data.get('active_percentage', 0)
                
                # Create summary bars
                fig_status.add_trace(
                    go.Bar(
                        x=['Active', 'Inactive'],
                        y=[total_active, total_inactive],
                        marker=dict(
                            color=['#2ecc71', '#e74c3c'],
                            line=dict(color='#2c3e50', width=1.5)
                        ),
                        text=[
                            f'{format_duration(total_active)}<br>({active_pct:.1f}%)',
                            f'{format_duration(total_inactive)}<br>({100-active_pct:.1f}%)'
                        ],
                        textposition='auto',
                        textfont=dict(size=12, color='white', family='Arial Black'),
                        showlegend=False,
                        hovertemplate=(
                            '<b>%{x}:</b> %{y:.1f} minutes<br>'
                            '<extra></extra>'
                        )
                    ),
                    row=2, col=1
                )
                
                # Update summary panel layout
                fig_status.update_xaxes(
                    title='',
                    showgrid=False,
                    row=2, col=1
                )
                fig_status.update_yaxes(
                    title='Time (minutes)',
                    gridcolor='#ecf0f1',
                    gridwidth=1,
                    showgrid=True,
                    row=2, col=1
                )
                
                # Overall layout customization
                fig_status.update_layout(
                    plot_bgcolor='white',
                    paper_bgcolor='white',
                    showlegend=True,
                    legend=dict(
                        orientation='h',
                        yanchor='bottom',
                        y=1.02,
                        xanchor='right',
                        x=1,
                        bgcolor='rgba(255,255,255,0.8)',
                        bordercolor='#2c3e50',
                        borderwidth=1
                    ),
                    height=500,
                    width=1000,
                    hovermode='closest',
                    margin=dict(l=60, r=60, t=100, b=60),
                    font=dict(family='Arial', size=11, color='#2c3e50')
                )
                
                # Add overall title annotation
                total_changes = status_report_data.get('total_changes', 0)
                fig_status.add_annotation(
                    text=f'Total Status Changes: {total_changes} | Uptime: {active_pct:.1f}%',
                    xref='paper', yref='paper',
                    x=0.5, y=1.08,
                    showarrow=False,
                    font=dict(size=13, color='#34495e'),
                    xanchor='center'
                )

                # Save status chart to buffer
                status_buffer = BytesIO()
                try:
                    fig_status.write_image(status_buffer, format='png', engine='kaleido', scale=2)
                    status_buffer.seek(0)
                    logger.info(f"Successfully generated enhanced status chart for {device_name}")
                except Exception as e:
                    logger.error(f"Error saving status chart to buffer for {device_name}: {str(e)}")
                    status_buffer = None
            else:
                logger.warning(f"No timeline data generated for status chart for device {device_name}")
        else:
            logger.info(f"No status data found or dataframe is empty for device {device_name}")

        return metrics_buffer, status_buffer, status_report_data
        
    except Exception as e:
        logger.error(f"Error generating charts or report data for {device_name}: {str(e)}")
        traceback.print_exc()
        return None, None, None