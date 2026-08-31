
import streamlit as st
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
import io

# 1. Define Geodetic Distance Formula
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0  # Earth's radius in km (Use 3958.8 for Miles)
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c

# 2. Main Streamlit Interface Layout
st.set_page_config(layout="wide")
st.title("🌐 Greenfield Center of Gravity (CoG) App")
st.markdown("Upload your customer address footprint to calculate optimal network hub locations.")

# Sidebar Settings Menu
st.sidebar.header("🔧 Settings Menu")
num_centers = st.sidebar.slider("Number of Centers to Identify", min_value=1, max_value=10, value=3)

# 3. File Upload Processing Panel
uploaded_file = st.file_uploader("Upload your Customer Footprint Excel Sheet", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        # Read the Excel data natively
        df_input = pd.read_excel(uploaded_file).fillna(0)
        
        # Enforce case-insensitive matching for mandatory geographic coordinates
        df_input.columns = [str(c).strip() for c in df_input.columns]
        required_cols = ['Name', 'Latitude', 'Longitude', 'Weight']
        
        if not all(col in df_input.columns for col in required_cols):
            st.error(f"Your Excel file columns must exactly match these headers: {required_cols}")
        else:
            # 4. Core Mathematical CoG Clustering Execution
            coordinates = df_input[['Latitude', 'Longitude']].values
            weights = df_input['Weight'].values
            
            # Execute K-Means algorithm using custom sample weights
            kmeans = KMeans(n_clusters=num_centers, random_state=42, n_init='auto')
            kmeans.fit(coordinates, sample_weight=weights)
            centers_output = kmeans.cluster_centers_
            df_input['Center_ID'] = kmeans.labels_
            
            # 5. Construct "CENTERS" Output Table
            centers_data = []
            for i, center in enumerate(centers_output):
                cluster_weight = df_input[df_input['Center_ID'] == i]['Weight'].sum()
                centers_data.append({
                    "Center Name": f"Center {i+1}",
                    "Center Latitude": center[0],
                    "Center Longitude": center[1],
                    "Weight": int(cluster_weight)
                })
            df_centers = pd.DataFrame(centers_data)
            
            # 6. Construct "ASSIGNED ADDRESSES" Output Table
            assigned_data = []
            for idx, row in df_input.iterrows():
                c_idx = row['Center_ID']
                c_lat = df_centers.loc[c_idx, 'Center Latitude']
                c_lon = df_centers.loc[c_idx, 'Center Longitude']
                c_name = df_centers.loc[c_idx, 'Center Name']
                
                # Dynamic great circle mileage tracking
                distance = haversine_distance(row['Latitude'], row['Longitude'], c_lat, c_lon)
                
                assigned_row = {
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
                    "Distance": round(distance, 2)
                }
                assigned_data.append(assigned_row)
            df_assigned = pd.DataFrame(assigned_data)
            
            # 7. Render UI Visualizations & KPI Cards
            st.success("Optimization Run Complete!")
            
            # Highlight Summary Performance Metrics
            kpi1, kpi2 = st.columns(2)
            kpi1.metric("Identified Hub Locations", f"{num_centers} Centers")
            kpi2.metric("Total Matrix Volume Handled", f"{int(df_input['Weight'].sum()):,}")
            
            # Render Clean Split Tables
            st.subheader("📊 Output Allocation Reports")
            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown("### CENTERS")
                st.dataframe(df_centers, use_container_width=True, hide_index=True)
            with col2:
                st.markdown("### ASSIGNED ADDRESSES")
                st.dataframe(df_assigned, use_container_width=True, hide_index=True)
            
            # 8. Multi-Tab Excel Workbook Generator Code Block
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_centers.to_excel(writer, sheet_name='Centers', index=False)
                df_assigned.to_excel(writer, sheet_name='Assigned Addresses', index=False)
            
            st.download_button(
                label="📥 Download Optimization Output Results Spreadsheet",
                data=buffer.getvalue(),
                file_name="Greenfield_CoG_Output.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            # 9. Spatial Network Mapping Coordinates View Canvas
            st.subheader("🗺️ Spatial Network Visualization Map")
            
            # Prepare plotting arrays
            map_data = []
            for _, r in df_assigned.iterrows():
                map_data.append({"lat": r["Latitude"], "lon": r["Longitude"], "type": "Customer", "size": 30})
            for _, c in df_centers.iterrows():
                map_data.append({"lat": c["Center Latitude"], "lon": c["Center Longitude"], "type": "Hub Center", "size": 150})
                
            df_map = pd.DataFrame(map_data)
            st.map(df_map, latitude="lat", longitude="lon", size="size")
            
    except Exception as e:
        st.error(f"Error executing logic sequence: {str(e)}")
else:
    st.info("Waiting for Excel workbook upload to execute calculation matrix.")
