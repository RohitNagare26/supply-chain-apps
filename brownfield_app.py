import streamlit as st
import pandas as pd
import numpy as np
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpStatus
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

def get_degressive_rate(dist, cost_1, cost_1000):
    if dist <= 0: return 0
    if dist >= 1000: return cost_1000
    slope = (cost_1 - cost_1000) / 1000.0
    return cost_1 - (slope * dist)

st.set_page_config(layout="wide")
st.title("🏭 Supply Chain Network Design Framework")
st.markdown("Download our baseline master structure template, ingest custom enterprise operational profiles, and deploy mixed-integer optimizations natively.")

if "scenarios" not in st.session_state: st.session_state.scenarios = {}
if "optimized" not in st.session_state: st.session_state.optimized = False
if "prob_results" not in st.session_state: st.session_state.prob_results = None

st.subheader("📋 1. Get the Optimization Ingest Template File")
dummy_buffer = io.BytesIO()
with pd.ExcelWriter(dummy_buffer, engine='openpyxl') as writer:
    pd.DataFrame([{"Name": "Cleveland Factory", "Latitude": 41.5051, "Longitude": -81.6934, "Truck Capacity Weight": 24000, "Truck Capacity Volume": 67, "Minimum FTL Costs": 0, "Truck Costs per km/mi [first km/mi]": 1.1, "Truck Costs per km/mi [1000 km/mi]": 0.7, "Minimum LTL Costs": 0, "Costs 1/2 Truck [%]": 65}]).to_excel(writer, sheet_name="Factories", index=False)
    pd.DataFrame([{"Name": "Tampa", "Latitude": 38.5472, "Longitude": -97.1530, "Fixed": 0, "Minimum Weight": 0, "Maximum Weight": 24000000, "Minimum Volume": 0, "Maximum Volume": 68000, "Fixed Costs": 150000, "Costs per Weight Unit": 0.003, "Costs per Volume Unit": 0.6, "Truck Capacity Weight": 24000, "Truck Capacity Volume": 67, "Truck Costs per km/mi [first km/mi]": 1.4, "Truck Costs per km/mi [1000 km/mi]": 1.05, "Minimum LTL Costs": 0, "Costs 1/2 Truck [%]": 70}]).to_excel(writer, sheet_name="Warehouses", index=False)
    pd.DataFrame([{"Name": "New York", "Latitude": 43.1561, "Longitude": -75.8449, "Weight": 20831, "Volume": 58, "Number of Shipments": 253, "Factory": "Cleveland Factory", "Warehouse": "", "Maximum Warehouse Distance": 2500}]).to_excel(writer, sheet_name="Customers", index=False)

st.download_button(label="📥 Download Sample Excel Template Workbook with Dummy Data", data=dummy_buffer.getvalue(), file_name="Supply_Chain_Template.xlsx")
st.markdown("---")
st.subheader("📤 2. Upload and Define Parameters")

st.sidebar.header("🔧 Settings Menu")
run_mode = st.sidebar.selectbox("Workflow Operational Mode", ["Run Network Optimization", "Run Current As-Is Baseline"])
max_wh = st.sidebar.slider("Maximum Allowed Open Warehouses", min_value=1, max_value=20, value=7)
dist_unit = st.sidebar.selectbox("Distance Calculation Metric", ["Kilometers", "Miles"])
line_thickness = st.sidebar.slider("Flow Path Line Thickness", min_value=1.0, max_value=5.0, value=2.0)

uploaded_file = st.file_uploader("Upload your completed company logistics sheet", type=["xlsx"])
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
                st.error("Invalid file structure. Column headers missing.")
                st.stop()
            headers = [str(h).strip() if pd.notna(h) else f"Empty_{i}" for i, h in enumerate(raw_df.iloc[header_idx])]
            data_body = raw_df.iloc[header_idx+1:].copy()
            data_body.columns = headers
            
            factories_df = data_body.iloc[:, 0:10].dropna(subset=['Name']).copy()
            factories_df.columns = ['Name', 'Latitude', 'Longitude', 'Truck Capacity Weight', 'Truck Capacity Volume', 'Minimum FTL Costs', 'Truck Costs per km/mi [first km/mi]', 'Truck Costs per km/mi [1000 km/mi]', 'Minimum LTL Costs', 'Costs 1/2 Truck [%]']
            warehouses_df = data_body.iloc[:, 11:28].dropna(subset=['Name']).copy()
            warehouses_df.columns = ['Name', 'Latitude', 'Longitude', 'Fixed', 'Minimum Weight', 'Maximum Weight', 'Minimum Volume', 'Maximum Volume', 'Fixed Costs', 'Costs per Weight Unit', 'Costs per Volume Unit', 'Truck Capacity Weight', 'Truck Capacity Volume', 'Truck Costs per km/mi [first km/mi]', 'Truck Costs per km/mi [1000 km/mi]', 'Minimum LTL Costs', 'Costs 1/2 Truck [%]']
            customers_df = data_body.iloc[:, 29:38].dropna(subset=['Name']).copy()
            customers_df.columns = ['Name', 'Latitude', 'Longitude', 'Weight', 'Volume', 'Number of Shipments', 'Factory', 'Warehouse', 'Maximum Warehouse Distance']
        else:
            factories_df = pd.read_excel(uploaded_file, sheet_name="Factories")
            warehouses_df = pd.read_excel(uploaded_file, sheet_name="Warehouses")
            customers_df = pd.read_excel(uploaded_file, sheet_name="Customers")

        for df in [factories_df, warehouses_df, customers_df]:
            df.columns = [str(c).strip() for c in df.columns]
            if 'Name' in df.columns: df['Name'] = df['Name'].astype(str).str.strip()
            for col in ['Latitude', 'Longitude', 'Weight', 'Volume', 'Fixed Costs', 'Maximum Weight', 'Number of Shipments', 'Costs per Weight Unit']:
                if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        factories_df = factories_df[factories_df['Latitude'] != 0].copy()
        warehouses_df = warehouses_df[warehouses_df['Latitude'] != 0].copy()
        customers_df = customers_df[customers_df['Latitude'] != 0].copy()

        facts = factories_df.set_index('Name').to_dict('index')
        whs = warehouses_df.set_index('Name').to_dict('index')
        custs = customers_df.set_index('Name').to_dict('index')

        unit_scale = 1.0 if dist_unit == "Kilometers" else 0.621371
        dist_fw = {f: {w: haversine_distance(facts[f]['Latitude'], facts[f]['Longitude'], whs[w]['Latitude'], whs[w]['Longitude']) * unit_scale for w in whs} for f in facts}
        dist_wc = {w: {c: haversine_distance(whs[w]['Latitude'], whs[w]['Longitude'], custs[c]['Latitude'], custs[c]['Longitude']) * unit_scale for c in custs} for w in whs}
        if st.button("🚀 Click to Execute Network Optimization Run"):
            with st.spinner("Executing capacity constraints linear program modeling..."):
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
                    st.session_state.optimized = True
                    wh_open_res = {w: use_w[w].varValue for w in whs}
                    flow_fw_res = {(f, w): flow_fw[f, w].varValue for f in facts for w in whs if flow_fw[f, w].varValue > 1.0}
                    flow_wc_res = {(w, c): flow_wc[w, c].varValue for w in whs for c in custs if flow_wc[w, c].varValue > 1.0}
                    
                    inbound_tot = sum([flow_fw_res.get((f, w), 0) * get_degressive_rate(dist_fw[f][w], facts[f].get('Truck Costs per km/mi [first km/mi]', 1), facts[f].get('Truck Costs per km/mi [1000 km/mi]', 1)) for f in facts for w in whs])
                    outbound_tot = sum([flow_wc_res.get((w, c), 0) * get_degressive_rate(dist_wc[w][c], whs[w].get('Truck Costs per km/mi [first km/mi]', 1), whs[w].get('Truck Costs per km/mi [1000 km/mi]', 1)) for w in whs for c in custs])
                    fixed_tot = sum([wh_open_res[w] * whs[w]['Fixed Costs'] for w in whs])
                    var_tot = sum([flow_wc_res.get((w, c), 0) * whs[w]['Costs per Weight Unit'] for w in whs for c in custs])
                    
                    st.session_state.prob_results = (int(prob.objective.value()), wh_open_res, flow_fw_res, flow_wc_res, inbound_tot, outbound_tot, fixed_tot, var_tot)
                else:
                    st.error("No optimal solution path found under current parameter ceilings.")
        if st.session_state.optimized:
            cost, wh_open, flow_fw_res, flow_wc_res, inbound_tot, outbound_tot, fixed_tot, var_tot = st.session_state.prob_results
            st.markdown("---")
            st.subheader("💾 Save This Configuration Run")
            scen_name = st.text_input("Type an identifiable label for this calculation", f"Scenario {len(st.session_state.scenarios)+1}")
            if st.button("Save to Comparison Room"):
                st.session_state.scenarios[scen_name] = {"cost": cost, "wh_open": wh_open, "flow_wc": flow_wc_res, "max_wh": max_wh, "unit": dist_unit}
                st.success(f"Pinned '{scen_name}' to system memory!")

            st.subheader("📊 3. Exploration Results Panel")
            tab_doc, tab_dash, tab_map = st.tabs(["📥 1. Download Excel Workbook", "📈 2. View Performance Dashboard", "🗺️ 3. View Interactive Network Map"])
            
            with tab_doc:
                st.markdown("### Output Generation Export Link")
                open_wh_rows = []
                for w in whs:
                    if wh_open[w] > 0.5:
                        w_wt = sum([flow_wc_res.get((w, c), 0) for c in custs])
                        w_vol = sum([flow_wc_res.get((w, c), 0) * (custs[c]['Volume'] / (custs[c]['Weight'] if custs[c]['Weight'] > 0 else 1)) for c in custs])
                        w_sh = sum([custs[c]['Number of Shipments'] for c in custs if flow_wc_res.get((w, c), 0) > 1.0])
                        open_wh_rows.append({"Name": w, "Assigned Weight": int(w_wt), "Assigned Volume": int(w_vol), "Assigned Shipments": int(w_sh), "Fixed Costs": int(whs[w]['Fixed Costs']), "Variable Costs": int(w_wt * whs[w]['Costs per Weight Unit'])})
                df_tab_wh = pd.DataFrame(open_wh_rows)
                
                f_w_rows = []
                for (f, w), val in flow_fw_res.items():
                    f_w_rows.append({"Factory Name": f, "Warehouse Name": w, "Weight": int(val), "Distance": round(dist_fw[f][w], 2), "Transport Costs": int(val * get_degressive_rate(dist_fw[f][w], facts[f].get('Truck Costs per km/mi [first km/mi]', 1), facts[f].get('Truck Costs per km/mi [1000 km/mi]', 1)))})
                df_tab_fw = pd.DataFrame(f_w_rows)

                w_c_rows = []
                for (w, c), val in flow_wc_res.items():
                    w_c_rows.append({"Name": c, "Weight": int(custs[c]['Weight']), "Volume": int(custs[c]['Volume']), "Number of Shipments": int(custs[c]['Number of Shipments']), "Warehouse Name": w, "Distance": round(dist_wc[w][c], 2), "Transport Costs": int(val * get_degressive_rate(dist_wc[w][c], whs[w].get('Truck Costs per km/mi [first km/mi]', 1), whs[w].get('Truck Costs per km/mi [1000 km/mi]', 1))), "Factory Name": custs[c]['Factory']})
                df_tab_wc = pd.DataFrame(w_c_rows)
                
                kpi_rows = [{"KPI Name": "Value Target Function", "Value": cost}, {"KPI Name": "Optimization Status", "Value": "optimal solution"}, {"KPI Name": "Total Transport Costs", "Value": int(inbound_tot + outbound_tot)}, {"KPI Name": "Fixed Warehouse Costs", "Value": int(fixed_tot)}, {"KPI Name": "Variable Warehouse Costs", "Value": int(var_tot)}]
                df_tab_kpi = pd.DataFrame(kpi_rows)

                out_buffer = io.BytesIO()
                with pd.ExcelWriter(out_buffer, engine='openpyxl') as writer:
                    df_tab_wh.to_excel(writer, sheet_name="Open Warehouses", index=False)
                    df_tab_fw.to_excel(writer, sheet_name="Factory-Warehouse Assignment", index=False)
                    df_tab_wc.to_excel(writer, sheet_name="Customer-Warehouse Assignment", index=False)
                    df_tab_kpi.to_excel(writer, sheet_name="KPIs", index=False)
                st.download_button(label="📥 Download Consolidated Optimized Solutions Workbook (Sheet 2 Format)", data=out_buffer.getvalue(), file_name="Optimized_Network_Output.xlsx")

            with tab_dash:
                st.markdown("### Executive Landed Cost Performance Dashboard")
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("TOTAL TARGET COSTS ($)", f"{cost:,}")
                k2.metric("TOTAL TRANSPORTATION ($)", f"{int(inbound_tot + outbound_tot):,}")
                k3.metric("FIXED WAREHOUSE LEASES ($)", f"{int(fixed_tot):,}")
                k4.metric("VARIABLE HANDLING OVERHEAD ($)", f"{int(var_tot):,}")
                
                st.markdown("#### Warehouse Performance & Allocation Cost Breakdown")
                perf_report = []
                for w in whs:
                    if wh_open[w] > 0.5:
                        cust_count = sum([1 for c in custs if flow_wc_res.get((w, c), 0) > 1.0])
                        w_wt = sum([flow_wc_res.get((w, c), 0) for c in custs])
                        f_cost = int(whs[w]['Fixed Costs'])
                        v_cost = int(w_wt * whs[w]['Costs per Weight Unit'])
                        perf_report.append({"Active Warehouse": w, "Customers Served": cust_count, "Fixed Operating Costs ($)": f_cost, "Variable Handling Costs ($)": v_cost, "Total Consolidated Warehouse Cost ($)": f_cost + v_cost})
                st.dataframe(pd.DataFrame(perf_report), use_container_width=True, hide_index=True)

            with tab_map:
                st.markdown("### Spatial Allocation Mapping System")
                v_lats = [whs[w]['Latitude'] for w in whs if wh_open[w] > 0.5] + [custs[c]['Latitude'] for c in custs]
                v_lons = [whs[w]['Longitude'] for w in whs if wh_open[w] > 0.5] + [custs[c]['Longitude'] for c in custs]
                map_obj = folium.Map(location=[np.mean(v_lats), np.mean(v_lons)], zoom_start=4)
                folium.TileLayer(tiles="https://{s}://{z}/{x}/{y}{r}.png", attr="&copy; CARTO", name="English labels", overlay=True, control=False).add_to(map_obj)
                
                fg_factories = folium.FeatureGroup(name="Factories (Red Pins)", show=True).add_to(map_obj)
                fg_warehouses = folium.FeatureGroup(name="Open Warehouses (Orange)", show=True).add_to(map_obj)
                fg_customers = folium.FeatureGroup(name="Customers (Blue)", show=True).add_to(map_obj)
                fg_inbound_lanes = folium.FeatureGroup(name="Inbound Lines (Red)", show=True).add_to(map_obj)
                fg_outbound_lanes = folium.FeatureGroup(name="Outbound Lines (Blue)", show=True).add_to(map_obj)
                
                for (f, w), val in flow_fw_res.items():
                    folium.PolyLine([[facts[f]['Latitude'], facts[f]['Longitude']], [whs[w]['Latitude'], whs[w]['Longitude']]], color="red", weight=line_thickness + 1, opacity=0.7).add_to(fg_inbound_lanes)
                for (w, c), val in flow_wc_res.items():
                    folium.PolyLine([[whs[w]['Latitude'], whs[w]['Longitude']], [custs[c]['Latitude'], custs[c]['Longitude']]], color="blue", weight=line_thickness, opacity=0.4).add_to(fg_outbound_lanes)
                    folium.CircleMarker([custs[c]['Latitude'], custs[c]['Longitude']], radius=4, color="blue", fill=True, popup=c).add_to(fg_customers)
                for f in facts:
                    folium.Marker([facts[f]['Latitude'], facts[f]['Longitude']], icon=folium.Icon(color="red", icon="industry", prefix="fa"), popup=f).add_to(fg_factories)
                for w in whs:
                    if wh_open[w] > 0.5: folium.Marker([whs[w]['Latitude'], whs[w]['Longitude']], icon=folium.Icon(color="orange", icon="warehouse", prefix="fa"), popup=w).add_to(fg_warehouses)
                    
                folium.LayerControl(position='topleft', collapsed=True).add_to(map_obj)
                st_folium(map_obj, width="100%", height=600, returned_objects=[], key="main_map")

        if len(st.session_state.scenarios) >= 2:
            st.markdown("---")
            st.subheader("⚖_ 4. Side-by-Side Scenario Comparison Room")
            scen_list = list(st.session_state.scenarios.keys())
            c1, c2 = st.columns(2)
            comp1 = c1.selectbox("Select Baseline Run (Left)", scen_list, index=0)
            comp2 = c2.selectbox("Select Challenger Run (Right)", scen_list, index=1)
            
            s1, s2 = st.session_state.scenarios[comp1], st.session_state.scenarios[comp2]
            col_left, col_right = st.columns(2)
            with col_left:
                st.markdown(f"### {comp1} Details")
                st.metric("Consolidated Costs ($)", f"{s1['cost']:,}")
                st.metric("Active Hub Count", f"{int(sum([s1['wh_open'][w] for w in whs]))} WH")
            with col_right:
                st.markdown(f"### {comp2} Details")
                st.markdown(f"### {comp2} Details")
                st.metric("Consolidated Costs ($)", f"{s2['cost']:,}", delta=int(s2['cost'] - s1['cost']), delta_color="inverse")
                st.metric("Active Hub Count", f"{int(sum([s2['wh_open'][w] for w in whs]))} WH")
    except Exception as e:
        st.error(f"Error compiling layout system: {str(e)}")
else:
    st.info("Awaiting master spreadsheet workbook upload to reveal control panels.")
