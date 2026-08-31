import streamlit as st
import pandas as pd
import numpy as np
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpStatus
import io
import folium
from streamlit_folium import st_folium

def haversine_distance(lat1, lon1, lat2, lon2):
    if lat1 == 0 or lon1 == 0 or lat2 == 0 or lon2 == 0: return 99999
    R = 6371.0 # km
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c

def get_degressive_rate(dist, cost_1, cost_1000):
    if dist <= 0: return 0
    if dist >= 1000: return cost_1000
    slope = (cost_1 - cost_1000) / 1000.0
    return cost_1 - (slope * dist)

st.set_page_config(layout="wide")
st.title("🏭 Brownfield Network Infrastructure Optimizer")
st.markdown("Upload your supply chain data sheet to execute capacity-constrained optimizations natively.")

st.sidebar.header("🔧 Optimization Settings")
run_mode = st.sidebar.selectbox("Workflow Operational Mode", ["Run Network Optimization", "Run Current As-Is Baseline"])
max_wh = st.sidebar.slider("Maximum Allowed Open Warehouses", min_value=1, max_value=20, value=7)

st.sidebar.markdown("---")
st.sidebar.header("🗺️ Map Layout Controls")
line_thickness = st.sidebar.slider("Flow Path Line Thickness", min_value=1.0, max_value=5.0, value=2.0)

uploaded_file = st.file_uploader("Upload your Supply Chain Excel Workbook (Single or Multi-Tab)", type=["xlsx"])
if uploaded_file is not None:
    try:
        xl = pd.ExcelFile(uploaded_file)
        if len(xl.sheet_names) == 1 or "Input" in xl.sheet_names or "Design" in xl.sheet_names:
            raw_df = pd.read_excel(uploaded_file, header=None)
            header_idx = None
            for idx, r in raw_df.iterrows():
                if "Name" in r.values:
                    header_idx = idx
                    break
            if header_idx is None:
                st.error("Invalid file structure. Could not find column header labels.")
                st.stop()
                
            headers = [str(h).strip() if pd.notna(h) else f"Empty_{i}" for i, h in enumerate(raw_df.iloc[header_idx])]
            data_body = raw_df.iloc[header_idx+1:].copy()
            data_body.columns = headers
            
            fact_cols = ['Name', 'Latitude', 'Longitude', 'Truck Capacity Weight', 'Truck Capacity Volume', 
                         'Minimum FTL Costs', 'Truck Costs per km/mi [first km/mi]', 'Truck Costs per km/mi [1000 km/mi]', 
                         'Minimum LTL Costs', 'Costs 1/2 Truck [%]']
            factories_df = data_body.iloc[:, 0:10].dropna(subset=['Name']).copy()
            factories_df.columns = fact_cols
            
            wh_cols = ['Name', 'Latitude', 'Longitude', 'Fixed', 'Minimum Weight', 'Maximum Weight', 
                       'Minimum Volume', 'Maximum Volume', 'Fixed Costs', 'Costs per Weight Unit', 
                       'Costs per Volume Unit', 'Truck Capacity Weight', 'Truck Capacity Volume', 
                       'Truck Costs per km/mi [first km/mi]', 'Truck Costs per km/mi [1000 km/mi]', 
                       'Minimum LTL Costs', 'Costs 1/2 Truck [%]']
            warehouses_df = data_body.iloc[:, 11:28].dropna(subset=['Name']).copy()
            warehouses_df.columns = wh_cols
            
            cust_cols = ['Name', 'Latitude', 'Longitude', 'Weight', 'Volume', 'Number of Shipments', 
                         'Factory', 'Warehouse', 'Maximum Warehouse Distance']
            customers_df = data_body.iloc[:, 29:38].dropna(subset=['Name']).copy()
            customers_df.columns = cust_cols
        else:
            factories_df = pd.read_excel(uploaded_file, sheet_name=xl.sheet_names[0])
            warehouses_df = pd.read_excel(uploaded_file, sheet_name=xl.sheet_names[1])
            customers_df = pd.read_excel(uploaded_file, sheet_name=xl.sheet_names[2])

        for df in [factories_df, warehouses_df, customers_df]:
            df.columns = [str(c).strip() for c in df.columns]
            if 'Name' in df.columns: 
                df['Name'] = df['Name'].astype(str).str.strip()
            for col in ['Latitude', 'Longitude', 'Weight', 'Volume', 'Fixed Costs', 'Maximum Weight']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                    
        factories_df = factories_df[factories_df['Latitude'] != 0].copy()
        warehouses_df = warehouses_df[warehouses_df['Latitude'] != 0].copy()
        customers_df = customers_df[customers_df['Latitude'] != 0].copy()

        facts = factories_df.set_index('Name').to_dict('index')
        whs = warehouses_df.set_index('Name').to_dict('index')
        custs = customers_df.set_index('Name').to_dict('index')

        dist_fw = {f: {w: haversine_distance(facts[f]['Latitude'], facts[f]['Longitude'], whs[w]['Latitude'], whs[w]['Longitude']) for w in whs} for f in facts}
        dist_wc = {w: {c: haversine_distance(whs[w]['Latitude'], whs[w]['Longitude'], custs[c]['Latitude'], custs[c]['Longitude']) for c in custs} for w in whs}
        prob = LpProblem("Brownfield_Optimization", LpMinimize)
        use_w = LpVariable.dicts("Open_WH", whs.keys(), cat="Binary")
        flow_fw = LpVariable.dicts("Flow_Fact_WH", [(f, w) for f in facts for w in whs], lowBound=0, cat="Continuous")
        flow_wc = LpVariable.dicts("Flow_WH_Cust", [(w, c) for w in whs for c in custs], lowBound=0, cat="Continuous")

        for w in whs:
            if whs[w].get('Fixed', 0) == 1: prob += use_w[w] == 1
        
        if run_mode == "Run Current As-Is Baseline":
            for c in custs:
                assigned_wh = str(custs[c].get('Warehouse', '0')).strip()
                if assigned_wh in whs:
                    prob += flow_wc[assigned_wh, c] == custs[c]['Weight'] * custs[c]['Number of Shipments']
                    prob += use_w[assigned_wh] == 1

        for c in custs:
            if run_mode == "Run Network Optimization":
                prob += lpSum([flow_wc[w, c] for w in whs]) == custs[c]['Weight'] * custs[c]['Number of Shipments']
            for w in whs:
                max_d = custs[c].get('Maximum Warehouse Distance', 99999)
                if max_d > 0 and dist_wc[w][c] > max_d: prob += flow_wc[w, c] == 0

        for w in whs:
            prob += lpSum([flow_fw[f, w] for f in facts]) == lpSum([flow_wc[w, c] for c in custs])
            prob += lpSum([flow_wc[w, c] for c in custs]) <= whs[w]['Maximum Weight'] * use_w[w]
            prob += lpSum([flow_wc[w, c] for c in custs]) >= whs[w]['Minimum Weight'] * use_w[w]

        prob += lpSum([use_w[w] for w in whs]) <= max_wh

        inbound_cost_expr = lpSum([flow_fw[f, w] * get_degressive_rate(dist_fw[f][w], facts[f].get('Truck Costs per km/mi [first km/mi]', 1), facts[f].get('Truck Costs per km/mi [1000 km/mi]', 1)) for f in facts for w in whs])
        outbound_cost_expr = lpSum([flow_wc[w, c] * get_degressive_rate(dist_wc[w][c], whs[w].get('Truck Costs per km/mi [first km/mi]', 1), whs[w].get('Truck Costs per km/mi [1000 km/mi]', 1)) for w in whs for c in custs])
        wh_fixed_expr = lpSum([use_w[w] * whs[w]['Fixed Costs'] for w in whs])
        wh_variable_expr = lpSum([flow_wc[w, c] * whs[w]['Costs per Weight Unit'] for w in whs for c in custs])

        prob += inbound_cost_expr + outbound_cost_expr + wh_fixed_expr + wh_variable_expr
        prob.solve()

        if LpStatus[prob.status] == "Optimal":
            st.success("Optimization Run Complete!")
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("Optimization Status", LpStatus[prob.status])
            kpi2.metric("Total System Cost ($)", f"{int(prob.objective.value()):,}")
            kpi3.metric("Open Warehouses", f"{int(sum([use_w[w].varValue for w in whs]))} Active")
            
            wh_report = []
            for w in whs:
                if use_w[w].varValue > 0.5:
                    wh_report.append({
                        "Warehouse Name": w, "Assigned Weight": int(sum([flow_wc[w, c].varValue for c in custs])),
                        "Fixed Costs": int(whs[w]['Fixed Costs']),
                        "Variable Costs": int(sum([flow_wc[w, c].varValue * whs[w]['Costs per Weight Unit'] for c in custs]))
                    })
            df_wh_out = pd.DataFrame(wh_report)
            st.subheader("📊 Facility Optimization Log")
            st.dataframe(df_wh_out, use_container_width=True, hide_index=True)

            st.subheader("🗺️ Network Optimization Flow Map")
            valid_lats = [whs[w]['Latitude'] for w in whs if use_w[w].varValue > 0.5] + [custs[c]['Latitude'] for c in custs]
            valid_lons = [whs[w]['Longitude'] for w in whs if use_w[w].varValue > 0.5] + [custs[c]['Longitude'] for c in custs]
            m = folium.Map(location=[np.mean(valid_lats), np.mean(valid_lons)], zoom_start=4, tiles="OpenStreetMap")
            folium.TileLayer(tiles="https://{s}://{z}/{x}/{y}{r}.png", attr="&copy; CARTO", name="English labels", overlay=True, control=False).add_to(m)
            
            fg_factories = folium.FeatureGroup(name="Factories (Red)", show=True).add_to(m)
            fg_warehouses = folium.FeatureGroup(name="Open Warehouses (Orange)", show=True).add_to(m)
            fg_customers = folium.FeatureGroup(name="Customers (Blue)", show=True).add_to(m)
            fg_inbound_lanes = folium.FeatureGroup(name="Inbound Lines (Red)", show=True).add_to(m)
            fg_outbound_lanes = folium.FeatureGroup(name="Outbound Lines (Blue)", show=True).add_to(m)
            
            for (f, w), f_val in flow_fw.items():
                if f_val.varValue > 1.0:
                    folium.PolyLine(locations=[[facts[f]['Latitude'], facts[f]['Longitude']], [whs[w]['Latitude'], whs[w]['Longitude']]], color="red", weight=line_thickness + 1, opacity=0.7).add_to(fg_inbound_lanes)
            for (w, c), f_val in flow_wc.items():
                if f_val.varValue > 1.0:
                    folium.PolyLine(locations=[[whs[w]['Latitude'], whs[w]['Longitude']], [custs[c]['Latitude'], custs[c]['Longitude']]], color="blue", weight=line_thickness, opacity=0.4).add_to(fg_outbound_lanes)
                    folium.CircleMarker(location=[custs[c]['Latitude'], custs[c]['Longitude']], radius=4, color="blue", fill=True, popup=f"Customer: {c}").add_to(fg_customers)
            for f in facts:
                folium.Marker(location=[facts[f]['Latitude'], facts[f]['Longitude']], icon=folium.Icon(color="red", icon="industry", prefix="fa"), popup=f"Factory: {f}").add_to(fg_factories)
            for w in whs:
                if use_w[w].varValue > 0.5:
                    folium.Marker(location=[whs[w]['Latitude'], whs[w]['Longitude']], icon=folium.Icon(color="orange", icon="warehouse", prefix="fa"), popup=f"Warehouse: {w}").add_to(fg_warehouses)
            
            folium.LayerControl(position='topleft', collapsed=True).add_to(m)
            st_folium(m, width="100%", height=650, returned_objects=[])
        else:
            st.error("The solver engine was unable to compute an optimal distribution pattern.")
    except Exception as e:
        st.error(f"Error parsing workbook layout matrix: {str(e)}")
else:
    st.info("Waiting for your optimization data sheet upload.")
