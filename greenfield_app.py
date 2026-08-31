import streamlit as st
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans

# 1. Define Haversine Distance Function
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0 # Earth radius in km (Change to 3958.8 for Miles if preferred)
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

# Sidebar Configuration Layout
st.sidebar.header("🔧 Settings Menu")
num_centers = st.sidebar.slider("Number of Centers to Identify", min_value=1, max_value=10, value=3)

# 3. File Upload Processing
uploaded_file = st.file_uploader("Upload your Customer Footprint Excel Sheet", type=["xlsx", "xls"])

if uploaded_file is not None:
    try:
        # Read the sheet natively (assuming sheet name or default first index)
        df_input = pd.read_excel(uploaded_file).fillna(0)
        
        # Verify essential geographical columns exist
        required_cols = ['Name', 'Latitude', 'Longitude', 'Weight']
        if not all(col in df_input.columns for col in required_cols):
            st.error(f"Your Excel file must contain these exact columns: {required_cols}")
        else:
            # 4. Core Mathematical CoG Clustering Execution
            coordinates = df_input[['Latitude', 'Longitude']].values
            weights = df_input['Weight'].values
            
            # Run Weighted K-Means to identify geographical center balancing volumes
            kmeans = KMeans(n_clusters=num_centers, random_state=42)
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
                    "Weight": cluster_weight
                })
            df_centers = pd.DataFrame(centers_data)
            
            # 6. Construct "ASSIGNED ADDRESSES" Output Table
            assigned_data = []
            for idx, row in df_input.iterrows():
                assigned_center_idx = row['Center_ID']
                c_lat = df_centers.loc[assigned_center_idx, 'Center Latitude']
                c_lon = df_centers.loc[assigned_center_idx, 'Center Longitude']
                c_name = df_centers.loc[assigned_center_idx, 'Center Name']
                
                # Calculate real physical distance to assigned hub
                distance = haversine_distance(row['Latitude'], row['Longitude'], c_lat, c_lon)
                
                # Pull original metadata flexibly based on what columns the user provided
                assigned_row = {
                    "Name": row['Name'],
                    "Country": row.get('Country', ''),
                    "State": row.get('State', ''),
                    "Zip": row.get('Zip', ''),
                    "City": row.get('City', ''),
                    "Street": row.get('Street', ''),
                    "Weight": row['Weight'],
                    "Latitude": row['Latitude'],
                    "Longitude": row['Longitude'],
                    "Center Name": c_name,
                    "Center Latitude": c_lat,
                    "Center Longitude": c_lon,
                    "Distance": distance
                }
                assigned_data.append(assigned_row)
            df_assigned = pd.DataFrame(assigned_data)
            
            # 7. Render UI Columns with Data Visuals
            st.success("Optimization Run Complete!")
            
            # Render Layout Tables
            col1, col2 = st.columns([1, 2])
            with col1:
                st.subheader("🎯 Calculated Centers")
                st.dataframe(df_centers, use_container_width=True)
            with col2:
                st.subheader("📦 Assigned Addresses Matrix")
                st.dataframe(df_assigned, use_container_width=True)
                
            # Render Geographical Map View Canvas
            st.subheader("🗺️ Spatial Network Visualization")
            # Separate mapping dataframe highlighting colors
            map_customers = df_input[['Latitude', 'Longitude']].copy()
            st.map(map_customers) # Simple integrated map plot
            
    except Exception as e:
        st.error(f"Error reading file structure: {str(e)}")
else:
    st.info("Waiting for Excel workbook upload to execute calculation matrix.")
