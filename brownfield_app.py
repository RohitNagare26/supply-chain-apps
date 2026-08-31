import streamlit as st
import pandas as pd
import numpy as np
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpStatus, HiGHS_CMD
import io
import folium
from streamlit_folium import st_folium

def haversine_distance(lat1, lon1, lat2, lon2):
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
st.markdown("Upload multi-tab network matrices to execute capacity-constrained mixed-integer optimizations via HiGHS.")

st.sidebar.header("🔧 Optimization Settings")
run_mode = st.sidebar.selectbox("Workflow Operational Mode", ["Run Network Optimization", "Run Current As-Is Baseline"])
max_wh = st.sidebar.slider("Maximum Allowed Open Warehouses", min_value=1, max_value=20, value=7)

st.sidebar.markdown("---")
st.sidebar.header("🗺️ Map Layout Controls")
line_thickness = st.sidebar.slider("Flow Path Line Thickness", min_value=1.0, max_value=5.0, value=2.0)

uploaded_file = st.file_uploader("Upload your Master Supply Chain Excel Workbook", type=["xlsx"])
if uploaded_file is not None:
    try:
        # Load explicit workbook tabs
        factories_df = pd.read_excel(uploaded_file, sheet_name="Factories").fillna(0)
        warehouses_df = pd.read_excel(uploaded_file, sheet_name="Warehouses").fillna(0)
        customers_df = pd.read_excel(uploaded_file, sheet_name="Customers").fillna(0)
        
        # Strip string white spaces
        for df in [factories_df, warehouses_df, customers_df]:
            df.columns = [str(c).strip() for c in df.columns]
            if 'Name' in df.columns: df['Name'] = df['Name'].astype(str).str.strip()

        # Build clean index dictionaries
        facts = factories_df.set_index('Name').to_dict('index')
        whs = warehouses_df.set_index('Name').to_dict('index')
        custs = customers_df.set_index('Name').to_dict('index')

        # Distance Grid Framework
        dist_fw = {f: {w: haversine_distance(facts[f]['Latitude'], facts[f]['Longitude'], whs[w]['Latitude'], whs[w]['Longitude']) for w in whs} for f in facts}
        dist_wc = {w: {c: haversine_distance(whs[w]['Latitude'], whs[w]['Longitude'], custs[c]['Latitude'], custs[c]['Longitude']) for c in custs} for w in whs}

        # Initialize linear programming problem
        prob = LpProblem("Brownfield_Optimization", LpMinimize)

        # Decision Variables
        use_w = LpVariable.dicts("Open_WH", whs.keys(), cat="Binary")
        flow_fw = LpVariable.dicts("Flow_Fact_WH", [(f, w) for f in facts for w in whs], lowBound=0, cat="Continuous")
        flow_wc = LpVariable.dicts("Flow_WH_Cust", [(w, c) for w in whs for c in custs], lowBound=0, cat="Continuous")

        # Handle hard-coded constraints for "Fixed" or "As-Is Baseline" parameters
        for w in whs:
            if whs[w].get('Fixed', 0) == 1:
                prob += use_w[w] == 1
        
        if run_mode == "Run Current As-Is Baseline":
            for c in custs:
                assigned_wh = str(custs[c].get('Warehouse', '0')).strip()
                if assigned_wh in whs:
                    prob += flow_wc[assigned_wh, c] == custs[c]['Weight'] * custs[c]['Number of Shipments']
                    prob += use_w[assigned_wh] == 1
                else:
                    st.error(f"Baseline customer entry '{c}' specifies an invalid warehouse target.")
                    st.stop()

        # Operational Constraints
        for c in custs:
            if run_mode == "Run Network Optimization":
                prob += lpSum([flow_wc[w, c] for w in whs]) == custs[c]['Weight'] * custs[c]['Number of Shipments']
            for w in whs:
                max_d = custs[c].get('Maximum Warehouse Distance', 99999)
                if dist_wc[w][c] > max_d:
                    prob += flow_wc[w, c] == 0

        for w in whs:
            prob += lpSum([flow_fw[f, w] for f in facts]) == lpSum([flow_wc[w, c] for c in custs])
            prob += lpSum([flow_wc[w, c] for c in custs]) <= whs[w]['Maximum Weight'] * use_w[w]
            prob += lpSum([flow_wc[w, c] for c in custs]) >= whs[w]['Minimum Weight'] * use_w[w]

        prob += lpSum([use_w[w] for w in whs]) <= max_wh

        # Calculate Transportation and Fixed Operating Coefficients
        inbound_cost_expr = lpSum([flow_fw[f, w] * get_degressive_rate(dist_fw[f][w], facts[f]['Truck Costs per km/mi [first km/mi]'], facts[f]['Truck Costs per km/mi [1000 km/mi]']) for f in facts for w in whs])
        outbound_cost_expr = lpSum([flow_wc[w, c] * get_degressive_rate(dist_wc[w][c], whs[w]['Truck Costs per km/mi [first km/mi]'], whs[w]['Truck Costs per km/mi [1000 km/mi]']) for w in whs for c in custs])
        wh_fixed_expr = lpSum([use_w[w] * whs[w]['Fixed Costs'] for w in whs])
        wh_variable_expr = lpSum([flow_wc[w, c] * whs[w]['Costs per Weight Unit'] for w in whs for c in custs])

        prob += inbound_cost_expr + outbound_cost_expr + wh_fixed_expr + wh_variable_expr

        # Run HiGHS Solver
        prob.solve(HiGHS_CMD(msg=False))

        if LpStatus[prob.status] == "Optimal":
            st.success("Optimization Run Complete!")
            
            # Construct summary card data metrics
            tot_fixed = sum([use_w[w].varValue * whs[w]['Fixed Costs'] for w in whs])
            tot_var = sum([flow_wc[w, c].varValue * whs[w]['Costs per Weight Unit'] for w in whs for c in custs])
            tot_trans = prob.objective.value() - (tot_fixed + tot_var)
            
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("Optimization Status", LpStatus[prob.status])
            kpi2.metric("Total System Cost ($)", f"{int(prob.objective.value()):,}")
            kpi3.metric("Open Warehouses", f"{int(sum([use_w[w].varValue for w in whs]))} Active")
            
            # Generate Open Warehouses Report Table
            wh_report = []
            for w in whs:
                if use_w[w].varValue > 0.5:
                    wh_report.append({
                        "Warehouse Name": w,
                        "Assigned Weight": sum([flow_wc[w, c].varValue for c in custs]),
                        "Fixed Costs": whs[w]['Fixed Costs'],
                        "Variable Costs": sum([flow_wc[w, c].varValue * whs[w]['Costs per Weight Unit'] for c in custs])
                    })
            df_wh_out = pd.DataFrame(wh_report)
            st.subheader("📊 Facility Optimization Log")
            st.dataframe(df_wh_out, use_container_width=True, hide_index=True)

            # Generate Interactive Routing Map
            st.subheader("🗺️ Network Optimization Flow Map")
            m = folium.Map(location=[39.8283, -98.5795], zoom_start=4, tiles="OpenStreetMap")
            folium.TileLayer(tiles="https://{s}://{z}/{x}/{y}{r}.png", attr="&copy; CARTO", name="English labels", overlay=True, control=False).add_to(m)
            
            fg_nodes = folium.FeatureGroup(name="Facilities & Nodes").add_to(m)
            fg_lanes = folium.FeatureGroup(name="Active Supply Lines").add_to(m)
            
            # Map Active Delivery Channels
            for (w, c), f_val in flow_wc.items():
                if f_val.varValue > 1.0:
                    folium.PolyLine(locations=[[whs[w]['Latitude'], whs[w]['Longitude']], [custs[c]['Latitude'], custs[c]['Longitude']]], color="blue", weight=line_thickness, opacity=0.6).add_to(fg_lanes)
                    folium.CircleMarker(location=[custs[c]['Latitude'], custs[c]['Longitude']], radius=4, color="blue", fill=True, popup=c).add_to(fg_nodes)
            
            for w in whs:
                if use_w[w].varValue > 0.5:
                    folium.Marker(location=[whs[w]['Latitude'], whs[w]['Longitude']], icon=folium.Icon(color="orange", icon="warehouse", prefix="fa"), popup=w).add_to(fg_nodes)
            
            folium.LayerControl(position='topleft', collapsed=True).add_to(m)
            st_folium(m, width="100%", height=650, returned_objects=[])
        else:
            st.error("HiGHS Solver engine was unable to compute a feasible solution for this model configuration.")
            
    except Exception as e:
        st.error(f"Error parsing workbook tabs: {str(e)}")
else:
    st.info("Waiting for multi-tab Input Excel workbook upload to parse parameters.")
