import streamlit as st
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
import io
import folium
from streamlit_folium import st_folium

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c

st.set_page_config(layout="wide")
st.title("🌐 Greenfield Center of Gravity (CoG) App")
st.markdown("Upload your customer footprint to calculate optimal network hub locations.")

st.sidebar.header("🔧 Settings Menu")
num_centers = st.sidebar.slider("Number of Centers to Identify", min_value=1, max_value=10, value=3)
st.sidebar.markdown("---")
st.sidebar.header("🎨 Customer Bubble Customization")
cust_color_mode = st.sidebar.selectbox("Color Theme Mode", ["Unique Cluster Colors", "Single Unified Color"])
cust_base_color = st.sidebar.color_picker("Pick Customer Bubble Color (Unified Mode)", "#1f77b4")
cust_size = st.sidebar.slider("Customer Bubble Base Size", min_value=2, max_value=15, value=5)
st.sidebar.markdown("---")
st.sidebar.header("🎯 Hub Center Customization")
hub_color = st.sidebar.selectbox("Hub Marker Base Color", ["orange", "red", "blue", "green", "black", "purple"])
hub_icon_style = st.sidebar.selectbox("Hub Icon Shape", ["star", "building", "warehouse", "flag"])
st.sidebar.markdown("---")
st.sidebar.header("📐 Relation Flow Line Customization")
line_thickness = st.sidebar.slider("Flow Line Path Thickness", min_value=0.5, max_value=5.0, value=1.5, step=0.5)
line_opacity = st.sidebar.slider("Flow Line Path Transparency", min_value=0.1, max_value=1.0, value=0.5, step=0.1)
line_style = st.sidebar.selectbox("Flow Line Path Style Pattern", ["Dashed", "Solid"])

cluster_colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'darkblue', 'darkgreen', 'cadetblue', 'gray']
uploaded_file = st.file_uploader("Upload your Customer Footprint Excel Sheet", type=["xlsx", "xls"])
if uploaded_file is not None:
    try:
        df_input = pd.read_excel(uploaded_file).fillna(0)
        df_input.columns = [str(c).strip() for c in df_input.columns]
        required_cols = ['Name', 'Latitude', 'Longitude', 'Weight']
        if not all(col in df_input.columns for col in required_cols):
            st.error(f"Your Excel file columns must exactly match these headers: {required_cols}")
        else:
            coordinates = df_input[['Latitude', 'Longitude']].values
            weights = df_input['Weight'].values
            kmeans = KMeans(n_clusters=num_centers, random_state=42, n_init='auto')
            kmeans.fit(coordinates, sample_weight=weights)
            centers_output = kmeans.cluster_centers_
            df_input['Center_ID'] = kmeans.labels_
            
            centers_data = []
            for i, center in enumerate(centers_output):
                cluster_weight = df_input[df_input['Center_ID'] == i]['Weight'].sum()
                centers_data.append({
                    "Center Name": f"Center {i+1}",
                    "Center Latitude": round(float(center[0]), 6),
                    "Center Longitude": round(float(center[1]), 6),
                    "Weight": int(cluster_weight)
                })
            df_centers = pd.DataFrame(centers_data)
            
            assigned_data = []
            for idx, row in df_input.iterrows():
                c_idx = int(row['Center_ID'])
                c_lat = df_centers.loc[c_idx, 'Center Latitude']
                c_lon = df_centers.loc[c_idx, 'Center Longitude']
                c_name = df_centers.loc[c_idx, 'Center Name']
                distance_val = haversine_distance(row['Latitude'], row['Longitude'], c_lat, c_lon)
                final_distance = round(float(distance_val), 2)
                display_color = cluster_colors[c_idx % len(cluster_colors)] if cust_color_mode == "Unique Cluster Colors" else cust_base_color
                assigned_data.append({
                    "Name": row['Name'], "Country": row.get('Country', ''), "State": row.get('State', ''),
                    "Zip": row.get('Zip', ''), "City": row.get('City', ''), "Street": row.get('Street', ''),
                    "Weight": int(row['Weight']), "Latitude": row['Latitude'], "Longitude": row['Longitude'],
                    "Center Name": c_name, "Center Latitude": c_lat, "Center Longitude": c_lon,
                    "Distance": final_distance, "Color": display_color
                })
            df_assigned = pd.DataFrame(assigned_data)
            st.success("Optimization Run Complete!")
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### CENTERS")
                st.dataframe(df_centers, use_container_width=True, hide_index=True)
            with col2:
                st.markdown("### ASSIGNED ADDRESSES")
                st.dataframe(df_assigned.drop(columns=['Color']), use_container_width=True, hide_index=True)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_centers.to_excel(writer, sheet_name='Centers', index=False)
                df_assigned.drop(columns=['Color']).to_excel(writer, sheet_name='Assigned Addresses', index=False)
            st.download_button(
                label="📥 Download Output Spreadsheet", data=buffer.getvalue(),
                file_name="Greenfield_CoG_Output.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            st.subheader("🗺️ Network Allocation Map")
            c_lat_avg = df_input['Latitude'].mean()
            c_lon_avg = df_input['Longitude'].mean()
            m = folium.Map(
                location=[c_lat_avg, c_lon_avg], zoom_start=5, control_scale=True,
                tiles="https://{s}://{z}/{x}/{y}{r}.png",
                attr='&copy; OpenStreetMap &copy; CARTO'
            )
            fg_locations = folium.FeatureGroup(name="Locations (Customers)", show=True).add_to(m)
            fg_relations = folium.FeatureGroup(name="Relations (Flow Lines)", show=True).add_to(m)
            fg_centers = folium.FeatureGroup(name="Center of Gravity (Hubs)", show=True).add_to(m)
            dash_pattern = '5, 5' if line_style == "Dashed" else None
            
            for _, customer in df_assigned.iterrows():
                cust_coords = [customer['Latitude'], customer['Longitude']]
                hub_coords = [customer['Center Latitude'], customer['Center Longitude']]
                color = customer['Color']
                folium.CircleMarker(
                    location=cust_coords, radius=cust_size, color=color, fill=True,
                    fill_color=color, fill_opacity=0.7, popup=customer['Name']
                ).add_to(fg_locations)
                folium.PolyLine(
                    locations=[cust_coords, hub_coords], color=color, weight=line_thickness,
                    opacity=line_opacity, dash_array=dash_pattern
                ).add_to(fg_relations)
                
            for _, hub in df_centers.iterrows():
                folium.Marker(
                    location=[hub['Center Latitude'], hub['Center Longitude']],
                    icon=folium.Icon(color=hub_color, icon=hub_icon_style, prefix='fa'),
                    popup=hub['Center Name']
                ).add_to(fg_centers)
                
            folium.LayerControl(position='topleft', collapsed=True).add_to(m)
            st_folium(m, width="100%", height=700, returned_objects=[])
    except Exception as e:
        st.error(f"Error executing logic sequence: {str(e)}")
else:
    st.info("Waiting for Excel workbook upload to execute calculation matrix.")
