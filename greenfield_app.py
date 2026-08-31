import streamlit as st
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
import io
import folium
from streamlit_folium import st_folium

# 1. Define Distance Function (Fixed for NumPy arrays)
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c

# 2. Page Configuration
st.set_page_config(layout="wide")
st.title("🌐 Greenfield Center of Gravity (CoG) App")
st.markdown("Upload your customer address footprint to calculate optimal network hub locations with interactive map layer visibility controls.")

# Sidebar Configuration
st.sidebar.header("🔧 Settings Menu")
num_centers = st.sidebar.slider("Number of Centers to Identify", min_value=1, max_value=10, value=3)

# Distinct color palette for map clusters
cluster_colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 'darkblue', 'darkgreen', 'cadetblue']

uploaded_file = st.file_uploader("Upload your Customer Footprint Excel Sheet", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        df_input = pd.read_excel(uploaded_file).fillna(0)
        df_input.columns = [str(c).strip() for c in df_input.columns]
        required_cols = ['Name', 'Latitude', 'Longitude', 'Weight']
        
        if not all(col in df_input.columns for col in required_cols):
            st.error(f"Your Excel file columns must exactly match these headers: {required_cols}")
        else:
            # 3. Compute Weighted Centers
            coordinates = df_input[['Latitude', 'Longitude']].values
            weights = df_input['Weight'].values
            
            kmeans = KMeans(n_clusters=num_centers, random_state=42, n_init='auto')
            kmeans.fit(coordinates, sample_weight=weights)
            centers_output = kmeans.cluster_centers_
            df_input['Center_ID'] = kmeans.labels_
            
            # 4. Create CENTERS Table
            centers_data = []
            for i, center in enumerate(centers_output):
                cluster_weight = df_input[df_input['Center_ID'] == i]['Weight'].sum()
                centers_data.append({
                    "Center Name": f"Center {i+1}",
                    "Center Latitude": float(center[0]),
                    "Center Longitude": float(center[1]),
                    "Weight": int(cluster_weight)
                })
            df_centers = pd.DataFrame(centers_data)
            
            # 5. Create ASSIGNED ADDRESSES Table
            assigned_data = []
            for idx, row in df_input.iterrows():
                c_idx = row['Center_ID']
                c_lat = df_centers.loc[c_idx, 'Center Latitude']
                c_lon = df_centers.loc[c_idx, 'Center Longitude']
                c_name = df_centers.loc[c_idx, 'Center Name']
                
                # Compute raw distance scalar
                distance_val = haversine_distance(row['Latitude'], row['Longitude'], c_lat, c_lon)
                # Convert the NumPy data type safely to a standard rounded float point
                final_distance = round(float(np.ravel(distance_val)[0]), 2)
                
                assigned_data.append({
                    "Name": row['Name'],
                    "Country": row.get('Country', ''),
                    "State": row.get('State', ''),
                    "Zip": row.get('Zip', ''),
                    "City": row.get('City', ''),
                    "Street": row.get('Street', ''),
                    "Weight": int(row['Weight']),
                    "Latitude": row['Latitude'],
                    "Longitude": row['Longitude'],
                    "Center Name": c_name,
                    "Center Latitude": c_lat,
                    "Center Longitude": c_lon,
                    "Distance": final_distance,
                    "Color": cluster_colors[c_idx % len(cluster_colors)]
                })
            df_assigned = pd.DataFrame(assigned_data)
            
            st.success("Optimization Run Complete!")
            
            # Split Data Display Layout Tables
            col1, col2 = st.columns()
            with col1:
                st.markdown("### CENTERS (Optimal Hub Locations)")
                st.dataframe(df_centers, use_container_width=True, hide_index=True)
            with col2:
                st.markdown("### ASSIGNED ADDRESSES")
                st.dataframe(df_assigned.drop(columns=['Color']), use_container_width=True, hide_index=True)
            
            # Excel Generation Buffers
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_centers.to_excel(writer, sheet_name='Centers', index=False)
                df_assigned.drop(columns=['Color']).to_excel(writer, sheet_name='Assigned Addresses', index=False)
            
            st.download_button(
                label="📥 Download Optimization Output Results Spreadsheet",
                data=buffer.getvalue(),
                file_name="Greenfield_CoG_Output.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            # 6. Advanced Mapping Layer with Toggle Feature Groups
            st.subheader("🗺️ Network Allocation Map (With Layer Visibility Toggles)")
            
            # Initialize core map object
            center_lat = df_input['Latitude'].mean()
            center_lon = df_input['Longitude'].mean()
            m = folium.Map(location=[center_lat, center_lon], zoom_start=5, control_scale=True)
            
            # Initialize separate isolatable feature groups for layer control menu
            fg_locations = folium.FeatureGroup(name="Locations (Customers)", show=True).add_to(m)
            fg_relations = folium.FeatureGroup(name="Relations (Flow Lines)", show=True).add_to(m)
            fg_centers = folium.FeatureGroup(name="Center of Gravity (Hubs)", show=True).add_to(m)
            
            # Populate Custom Layer Visibility Nodes
            for _, customer in df_assigned.iterrows():
                cust_coords = [customer['Latitude'], customer['Longitude']]
                hub_coords = [customer['Center Latitude'], customer['Center Longitude']]
                color = customer['Color']
                
                # Plot customer point node into Locations group layer
                folium.CircleMarker(
                    location=cust_coords,
                    radius=5,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.7,
                    popup=f"<b>Customer:</b> {customer['Name']}<br>Weight: {customer['Weight']}<br>Assigned to: {customer['Center Name']}"
                ).add_to(fg_locations)
                
                # Draw the network path connecting line into Relations group layer
                folium.PolyLine(
                    locations=[cust_coords, hub_coords],
                    color=color,
                    weight=1.5,
                    opacity=0.5,
                    dash_array='5, 5'
                ).add_to(fg_relations)
                
            # Plot the main calculated CoG Hub Centers into Hubs group layer
            for _, hub in df_centers.iterrows():
                folium.Marker(
                    location=[hub['Center Latitude'], hub['Center Longitude']],
                    popup=f"<b>{hub['Center Name']}</b><br>Total Regional Capacity Throughput: {hub['Weight']:,}",
                    icon=folium.Icon(color='orange', icon='star', prefix='fa')
                ).add_to(fg_centers)
            
            # Add Interactive On/Off Toggle Menu Controls directly on the map surface
            folium.LayerControl(position='topleft', collapsed=False).add_to(m)
            
            # Display map object inside container canvas
            st_folium(m, width="100%", height=700, returned_objects=[])
            
    except Exception as e:
        st.error(f"Error executing logic sequence: {str(e)}")
else:
    st.info("Waiting for Excel workbook upload to execute calculation matrix.")
