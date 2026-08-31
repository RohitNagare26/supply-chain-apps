import streamlit as st
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
import io
import folium
from streamlit_folium import st_folium

def haversine_distance(lat1, lon1, lat2, lon2):
    if lat1 == 0 or lon1 == 0 or lat2 == 0 or lon2 == 0: return 99999
    R = 6371.0  # km
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c

st.set_page_config(layout="wide")
st.title("🌐 Greenfield Center of Gravity (CoG) Framework")
st.markdown("Download our master footprint layout, ingest custom customer destination coordinates, and execute demand-weighted multi-facility location clustering.")

# --- STEP 1: INITIALIZE MEMORY LOGS ---
if "cog_scenarios" not in st.session_state: st.session_state.cog_scenarios = {}
if "cog_optimized" not in st.session_state: st.session_state.cog_optimized = False
if "cog_results" not in st.session_state: st.session_state.cog_results = None

# --- STEP 2: DOWNLOAD BLANK DATA TEMPLATE ---
st.subheader("📋 1. Get the CoG Customer Footprint Template")
dummy_buffer = io.BytesIO()
with pd.ExcelWriter(dummy_buffer, engine='openpyxl') as writer:
    pd.DataFrame([
        {"Name": "Mumbai Core", "Country": "IN", "State": "MH", "Zip": "400001", "City": "Mumbai", "Street": "Main St", "Weight": 50000, "Latitude": 18.9220, "Longitude": 72.8347},
        {"Name": "Delhi Hub", "Country": "IN", "State": "DL", "Zip": "110001", "City": "Delhi", "Street": "Ring Rd", "Weight": 75000, "Latitude": 28.6139, "Longitude": 77.2090},
        {"Name": "Bangalore Outlet", "Country": "IN", "State": "KA", "Zip": "560001", "City": "Bangalore", "Street": "MG Rd", "Weight": 35000, "Latitude": 12.9716, "Longitude": 77.5946}
    ]).to_excel(writer, sheet_name="Customers", index=False)

st.download_button(label="📥 Download Sample Excel Template Workbook with Dummy Data", data=dummy_buffer.getvalue(), file_name="CoG_Customer_Template.xlsx")
st.markdown("---")
st.subheader("📤 2. Upload and Define Parameters")

st.sidebar.header("🔧 Settings Menu")
num_centers = st.sidebar.slider("Exact Number of Hubs to Identify", min_value=1, max_value=10, value=3)
dist_unit = st.sidebar.selectbox("Distance Calculation Metric", ["Kilometers", "Miles"])

st.sidebar.markdown("---")
st.sidebar.header("🎨 Customer Bubble Customization")
cust_color_mode = st.sidebar.selectbox("Color Theme Mode", ["Unique Cluster Colors", "Single Unified Color"])
cust_base_color = st.sidebar.color_picker("Pick Customer Bubble Color (Unified Mode)", "#1f77b4")
cust_size = st.sidebar.slider("Customer Bubble Base Size", min_value=2, max_value=15, value=5)

st.sidebar.markdown("---")
st.sidebar.header("📐 Relation Flow Line Customization")
line_thickness = st.sidebar.slider("Flow Line Path Thickness", min_value=0.5, max_value=5.0, value=1.5, step=0.5)
line_opacity = st.sidebar.slider("Flow Line Path Transparency", min_value=0.1, max_value=1.0, value=0.5, step=0.1)

cluster_colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'darkblue', 'darkgreen', 'cadetblue', 'gray']
uploaded_file = st.file_uploader("Upload your completed company customer footprint sheet", type=["xlsx", "xls"])
if uploaded_file is not None:
    try:
        df_input = pd.read_excel(uploaded_file).fillna(0)
        df_input.columns = [str(c).strip() for c in df_input.columns]
        
        # --- DATA INTEGRITY & STRUCTURAL AUDIT ENGINE ---
        validation_passed = True
        error_logs = []
        required_cols = ['Name', 'Latitude', 'Longitude', 'Weight']
        
        if not all(col in df_input.columns for col in required_cols):
            st.error(f"❌ **Column Header Mapping Failure**: Your file must contain these exact headers: {required_cols}")
            st.stop()

        for idx, row in df_input.iterrows():
            cust_lat = pd.to_numeric(row.get('Latitude', 0), errors='coerce') or 0
            cust_lon = pd.to_numeric(row.get('Longitude', 0), errors='coerce') or 0
            cust_wt = pd.to_numeric(row.get('Weight', 0), errors='coerce') or 0
            
            if cust_lat == 0 or cust_lon == 0:
                error_logs.append(f"⚠️ **Missing Coordinates**: Entry Line {idx+2} ('{row['Name']}') is missing valid Latitude or Longitude parameters.")
                validation_passed = False
            if cust_wt <= 0:
                error_logs.append(f"❌ **Weight Contradiction**: Entry Line {idx+2} ('{row['Name']}') lists an empty or negative volume constraint ({cust_wt}).")
                validation_passed = False

        if not validation_passed:
            st.error("🛑 Ingestion Terminated: Mathematical contradictions or empty values found in your spreadsheet layout. Review the checklist below:")
            for log in error_logs: st.markdown(log)
            st.stop()
        else:
            st.sidebar.success("✅ Customer Footprint Verified!")

        for col in ['Latitude', 'Longitude', 'Weight']:
            df_input[col] = pd.to_numeric(df_input[col], errors='coerce').fillna(0)
        df_input = df_input[df_input['Latitude'] != 0].copy()
        if st.button("🚀 Click to Execute Greenfield Center of Gravity Run"):
            with st.spinner("Calculating demand-weighted spatial geographic matrices..."):
                coordinates = df_input[['Latitude', 'Longitude']].values
                weights = df_input['Weight'].values
                
                # Fit K-Means algorithm using user physical sample demand weights
                kmeans = KMeans(n_clusters=num_centers, random_state=42, n_init='auto')
                kmeans.fit(coordinates, sample_weight=weights)
                centers_output = kmeans.cluster_centers_
                df_input['Center_ID'] = kmeans.labels_
                
                # Freeze and structure outputs
                st.session_state.cog_optimized = True
                st.session_state.cog_results = (centers_output, df_input.copy())

        if st.session_state.cog_optimized:
            centers_output, df_compiled = st.session_state.cog_results
            st.markdown("---")
            st.subheader("💾 Save This Configuration Run")
            scen_name = st.text_input("Type an identifiable label for this calculation", f"Scenario {len(st.session_state.cog_scenarios)+1}")
            
            if st.button("Save to Storage Vault"):
                st.session_state.cog_scenarios[scen_name] = {
                    "centers": centers_output, "df": df_compiled.copy(), "num": num_centers, "unit": dist_unit
                }
                st.success(f"Pinned '{scen_name}' to system memory vaults successfully!")
            # --- CONSTRUCT DATAFRAMES FOR INTERFACE ---
            df_centers_list = []
            for i, center in enumerate(centers_output):
                cluster_weight = df_compiled[df_compiled['Center_ID'] == i]['Weight'].sum()
                df_centers_list.append({"Center Name": f"Center {i+1}", "Center Latitude": round(float(center[0]), 6), "Center Longitude": round(float(center[1]), 6), "Weight Capacity Throughput": int(cluster_weight)})
            df_centers = pd.DataFrame(df_centers_list)

            unit_scale = 1.0 if dist_unit == "Kilometers" else 0.621371
            df_assigned_list = []
            for idx, row in df_compiled.iterrows():
                c_idx = int(row['Center_ID'])
                c_lat = df_centers.loc[c_idx, 'Center Latitude']
                c_lon = df_centers.loc[c_idx, 'Center Longitude']
                c_name = df_centers.loc[c_idx, 'Center Name']
                
                distance_val = haversine_distance(row['Latitude'], row['Longitude'], c_lat, c_lon) * unit_scale
                display_color = cluster_colors[c_idx % len(cluster_colors)] if cust_color_mode == "Unique Cluster Colors" else cust_base_color
                
                df_assigned_list.append({
                    "Name": row['Name'], "Country": row.get('Country', ''), "State": row.get('State', ''), "Zip": row.get('Zip', ''), "City": row.get('City', ''), "Street": row.get('Street', ''),
                    "Weight": int(row['Weight']), "Latitude": row['Latitude'], "Longitude": row['Longitude'],
                    "Center Name": c_name, "Center Latitude": c_lat, "Center Longitude": c_lon, "Distance": round(float(distance_val), 2), "Color": display_color
                })
            df_assigned = pd.DataFrame(df_assigned_list)

            st.subheader("📊 3. Exploration Results Panel")
            tab_doc, tab_dash, tab_map = st.tabs(["📥 1. Download Excel Workbook", "📈 2. View Performance Dashboard", "🗺️ 3. View Interactive Network Map"])
            
            with tab_doc:
                st.markdown("### Output Generation Export Link")
                out_buffer = io.BytesIO()
                with pd.ExcelWriter(out_buffer, engine='openpyxl') as writer:
                    df_centers.to_excel(writer, sheet_name="Centers", index=False)
                    df_assigned.drop(columns=['Color']).to_excel(writer, sheet_name="Assigned Addresses", index=False)
                st.download_button(label="📥 Download Consolidated Optimized Solutions Workbook", data=out_buffer.getvalue(), file_name="Greenfield_CoG_Output.xlsx")

            with tab_dash:
                st.markdown("### Executive Geographic Distribution Performance Dashboard")
                k1, k2 = st.columns(2)
                k1.metric("Calculated Central Hub Nodes", f"{num_centers} Optimal Hubs")
                k2.metric("Total Regional Tonnage Processed", f"{int(df_input['Weight'].sum()):,}")
                st.dataframe(df_centers, use_container_width=True, hide_index=True)

            with tab_map:
                st.markdown("### Spatial Allocation Mapping System")
                map_obj = folium.Map(location=[df_compiled['Latitude'].mean(), df_compiled['Longitude'].mean()], zoom_start=5)
                folium.TileLayer(tiles="https://{s}://{z}/{x}/{y}{r}.png", attr="&copy; CARTO", name="Labels", overlay=True, control=False).add_to(map_obj)
                
                fg_locations = folium.FeatureGroup(name="Locations (Customers)", show=True).add_to(map_obj)
                fg_relations = folium.FeatureGroup(name="Relations (Flow Lines)", show=True).add_to(map_obj)
                fg_centers = folium.FeatureGroup(name="Center of Gravity (Hubs)", show=True).add_to(map_obj)
                
                for _, cust in df_assigned.iterrows():
                    folium.CircleMarker([cust['Latitude'], cust['Longitude']], radius=cust_size, color=cust['Color'], fill=True).add_to(fg_locations)
                    folium.PolyLine([[cust['Latitude'], cust['Longitude']], [cust['Center Latitude'], cust['Center Longitude']]], color=cust['Color'], weight=line_thickness, opacity=line_opacity, dash_array='5, 5').add_to(fg_relations)
                for _, hub in df_centers.iterrows():
                    folium.Marker([hub['Center Latitude'], hub['Center Longitude']], icon=folium.Icon(color="orange", icon="star", prefix="fa"), popup=hub['Center Name']).add_to(fg_centers)
                
                folium.LayerControl(position='topleft', collapsed=True).add_to(map_obj)
                st_folium(map_obj, width="100%", height=600, returned_objects=[], key="main_map")
        if len(st.session_state.cog_scenarios) > 0:
            st.sidebar.markdown("---")
            st.sidebar.header("📁 Saved Scenarios Vault")
            view_scen = st.sidebar.selectbox("Quick-Inspect Saved Scenario Details", ["-- Select Scenario --"] + list(st.session_state.cog_scenarios.keys()))
            if view_scen != "-- Select Scenario --":
                sc = st.session_state.cog_scenarios[view_scen]
                st.markdown(f"### 🔍 Vault Inspection View: {view_scen}")
                st.write(f"Target Configuration Parameters: Calculated {sc['num']} Hub Centers using {sc['unit']}.")

        if len(st.session_state.cog_scenarios) >= 2:
            st.sidebar.markdown("---")
            st.sidebar.header("⚖️ Comparison Room Settings")
            show_comparison = st.sidebar.checkbox("Activate Side-by-Side Comparison Screen", value=False)
            
            if show_comparison:
                st.markdown("---")
                st.subheader("⚖️ 4. Side-by-Side Scenario Comparison Room")
                scen_list = list(st.session_state.cog_scenarios.keys())
                c1, c2 = st.columns(2)
                comp1 = c1.selectbox("Select Baseline Run (Left Column)", scen_list, index=0)
                comp2 = c2.selectbox("Select Challenger Run (Right Column)", scen_list, index=1)
                
                s1, s2 = st.session_state.cog_scenarios[comp1], st.session_state.cog_scenarios[comp2]
                col_left, col_right = st.columns(2)
                
                with col_left:
                    st.markdown(f"### 📈 {comp1} Details")
                    st.write(f"Calculated Core Facility Footprints: {s1['num']} Hub Centers")
                    m1 = folium.Map(location=[df_compiled['Latitude'].mean(), df_compiled['Longitude'].mean()], zoom_start=4)
                    folium.TileLayer("https://{s}://{z}/{x}/{y}{r}.png", attr="&copy; CARTO", name="Labels", overlay=True, control=False).add_to(m1)
                    
                    f1_c = folium.FeatureGroup(name="Customers", show=True).add_to(m1)
                    f1_h = folium.FeatureGroup(name="Hubs", show=True).add_to(m1)
                    f1_l = folium.FeatureGroup(name="Lanes", show=True).add_to(m1)
                    
                    for i, center in enumerate(s1['centers']):
                        folium.Marker([center[0], center[1]], icon=folium.Icon(color="red", icon="star")).add_to(f1_h)
                    for _, r in s1['df'].iterrows():
                        folium.CircleMarker([r['Latitude'], r['Longitude']], radius=4, color="red").add_to(f1_c)
                        c_lat = float(s1['centers'][int(r['Center_ID'])][0])
                        c_lon = float(s1['centers'][int(r['Center_ID'])][1])
                        folium.PolyLine([[r['Latitude'], r['Longitude']], [c_lat, c_lon]], color="red", weight=1.5, dash_array='5,5').add_to(f1_l)
                    
                    folium.LayerControl(position='topleft', collapsed=True).add_to(m1)
                    st_folium(m1, width="100%", height=400, key="map_left_cog", returned_objects=[])
                    
                with col_right:
                    st.markdown(f"### 📈 {comp2} Details")
                    st.write(f"Calculated Core Facility Footprints: {s2['num']} Hub Centers")
                    m2 = folium.Map(location=[df_compiled['Latitude'].mean(), df_compiled['Longitude'].mean()], zoom_start=4)
                    folium.TileLayer("https://{s}://{z}/{x}/{y}{r}.png", attr="&copy; CARTO", name="Labels", overlay=True, control=False).add_to(m2)
                    
                    f2_c = folium.FeatureGroup(name="Customers", show=True).add_to(m2)
                    f2_h = folium.FeatureGroup(name="Hubs", show=True).add_to(m2)
                    f2_l = folium.FeatureGroup(name="Lanes", show=True).add_to(m2)
                    
                    for i, center in enumerate(s2['centers']):
                        folium.Marker([center[0], center[1]], icon=folium.Icon(color="green", icon="star")).add_to(f2_h)
                    for _, r in s2['df'].iterrows():
                        folium.CircleMarker([r['Latitude'], r['Longitude']], radius=4, color="green").add_to(f2_c)
                        c_lat = float(s2['centers'][int(r['Center_ID'])][0])
                        c_lon = float(s2['centers'][int(r['Center_ID'])][1])
                        folium.PolyLine([[r['Latitude'], r['Longitude']], [c_lat, c_lon]], color="green", weight=1.5, dash_array='5,5').add_to(f2_l)
                    
                    folium.LayerControl(position='topleft', collapsed=True).add_to(m2)
                    st_folium(m2, width="100%", height=400, key="map_right_cog", returned_objects=[])

    except Exception as e:
        st.error(f"Error compiling layout system: {str(e)}")
else:
    st.info("Awaiting customer address footprint spreadsheet upload to reveal parameters.")
