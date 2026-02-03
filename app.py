import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta, datetime
from supabase import create_client
import io

# --- 1. CONFIGURACIÓN INICIAL Y DISEÑO ---
st.set_page_config(page_title="Agrícola Montserrat", layout="wide", page_icon="🍌")

# --- 🎨 INYECCIÓN DE CSS (DISEÑO) ---
st.markdown("""
    <style>
    /* Fondo general suave */
    .stApp {
        background-color: #f8fcf8;
    }
    
    /* Títulos Principales en Verde Agrícola */
    h1, h2, h3 {
        color: #1b5e20 !important;
        font-family: 'Helvetica Neue', sans-serif;
    }
    
    /* Tarjetas para las Métricas (KPIs) */
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #c8e6c9;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
        text-align: center;
    }
    
    /* Etiquetas de las métricas */
    div[data-testid="stMetricLabel"] {
        color: #388e3c;
        font-weight: bold;
    }

    /* Botones principales (Guardar/Actualizar) */
    .stButton>button {
        background-color: #2e7d32;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 10px 20px;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #1b5e20;
        color: white;
    }

    /* Pestañas (Tabs) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #ffffff;
        border-radius: 5px 5px 0 0;
        padding: 10px 20px;
        border: 1px solid #e0e0e0;
    }
    .stTabs [aria-selected="true"] {
        background-color: #e8f5e9 !important;
        color: #1b5e20 !important;
        border-bottom: 2px solid #2e7d32 !important;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e0e0e0;
    }
    </style>
""", unsafe_allow_html=True)

# --- 🔒 BLOQUE DE SEGURIDAD ---
def check_password():
    if st.session_state["password_input"] == st.secrets["APP_PASSWORD"]:
        st.session_state["password_correct"] = True
        del st.session_state["password_input"]
    else:
        st.error("😕 Clave incorrecta, intenta de nuevo.")

if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False

if not st.session_state["password_correct"]:
    st.title("🔐 Acceso Restringido")
    st.markdown("### Agrícola Montserrat 2026")
    st.text_input("Ingresa la clave maestra:", type="password", key="password_input", on_change=check_password)
    st.stop()

# --- CONEXIÓN A SUPABASE ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except:
    st.error("⚠️ Faltan las credenciales de Supabase en los Secrets.")
    st.stop()

@st.cache_resource
def init_connection():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.error(f"Error conectando con Supabase: {e}")
        return None

supabase = init_connection()
BUCKET_FACTURAS = "facturas" 

# --- 2. FUNCIONES DE LÓGICA ---

@st.cache_data(ttl=60) 
def cargar_ventas():
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table("ventas_2026").select("*").order("fecha", desc=True).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            mapa_cols = {
                'id': 'ID', 'fecha': 'Fecha', 'producto': 'Producto', 'proveedor': 'Proveedor', 
                'cliente': 'Cliente', 'fec_doc_url': 'FEC_Doc', 'fev_doc_url': 'FEV_Doc', 
                'kg_compra': 'Kg_Compra', 'precio_compra': 'Precio_Compra', 'fletes': 'Fletes',
                'viaticos': 'Viaticos', 'otros_gastos': 'Otros_Gastos', 'kg_venta': 'Kg_Venta',
                'precio_venta': 'Precio_Venta', 'retenciones': 'Retenciones', 'descuentos': 'Descuentos',
                'utilidad': 'Utilidad', 'estado_pago': 'Estado_Pago', 'dias_credito': 'Dias_Credito',
                'precio_plaza': 'Precio_Plaza'
            }
            df = df.rename(columns={k: v for k, v in mapa_cols.items() if k in df.columns})
            if 'Fecha' in df.columns: df['Fecha'] = pd.to_datetime(df['Fecha'])
            
            cols_url = ['FEC_Doc', 'FEV_Doc']
            for col in cols_url:
                if col in df.columns: df[col] = df[col].replace({'': None, 'None': None, 'nan': None})
            
            if 'Precio_Plaza' not in df.columns: df['Precio_Plaza'] = 0.0
            else: df['Precio_Plaza'] = pd.to_numeric(df['Precio_Plaza']).fillna(0.0)

            return df
    except: return pd.DataFrame()
    return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_gastos():
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table("gastos_fijos_2026").select("*").order("fecha", desc=True).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df = df.rename(columns={'id': 'ID', 'fecha': 'Fecha', 'concepto': 'Concepto', 'monto': 'Monto'})
            df['Fecha'] = pd.to_datetime(df['Fecha'])
            return df
    except: return pd.DataFrame()
    return pd.DataFrame()

def subir_archivo(archivo, nombre_base):
    if archivo and supabase:
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            nombre_clean = "".join(c for c in archivo.name if c.isalnum() or c in "._-")
            nombre_archivo = f"{nombre_base}_{timestamp}_{nombre_clean}"
            archivo_bytes = archivo.getvalue()
            supabase.storage.from_(BUCKET_FACTURAS).upload(path=nombre_archivo, file=archivo_bytes, file_options={"content-type": archivo.type})
            return supabase.storage.from_(BUCKET_FACTURAS).get_public_url(nombre_archivo)
        except Exception as e:
            st.error(f"Error subiendo: {e}")
            return None
    return None

def color_deuda(row):
    color = ''
    try:
        if row['Estado_Pago'] == 'Pagado': color = 'background-color: #e8f5e9; color: #1b5e20; font-weight: bold;'
        elif row['Estado_Pago'] == 'Pendiente':
            dias = int(row['Dias_Credito']) if pd.notnull(row['Dias_Credito']) else 0
            vence = row['Fecha'] + timedelta(days=dias)
            dias_rest = (vence.date() - date.today()).days
            if dias_rest < 0: color = 'background-color: #ffebee; color: #b71c1c; font-weight: bold;' 
            elif dias_rest <= 3: color = 'background-color: #fff8e1; color: #f57f17; font-weight: bold;'
    except: pass
    return [color] * len(row)

def obtener_opciones(df, col, defaults):
    existentes = df[col].unique().tolist() if not df.empty and col in df.columns else []
    return sorted(list(set(defaults + [x for x in existentes if x])))

@st.cache_data
def convertir_df_a_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# --- INICIO INTERFAZ ---
st.markdown("# 🍌 Agrícola Montserrat")
st.markdown("### _Sistema de Gestión Integral 2026_")
st.markdown("---")

# SIDEBAR
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2909/2909798.png", width=50)
st.sidebar.title("Menú")
st.sidebar.header("⚙️ Configuración")
if st.sidebar.button("🔄 Actualizar Datos"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.divider()
f_ini = st.sidebar.date_input("📅 Inicio", date(2026, 1, 1))
f_fin = st.sidebar.date_input("📅 Fin", date(2026, 12, 31))

df_ventas = cargar_ventas()
df_gastos = cargar_gastos()

# FILTROS
if not df_ventas.empty:
    mask_v = (df_ventas['Fecha'].dt.date >= f_ini) & (df_ventas['Fecha'].dt.date <= f_fin)
    df_v_filtrado = df_ventas.loc[mask_v].copy()
else: df_v_filtrado = pd.DataFrame(columns=df_ventas.columns)

if not df_gastos.empty:
    mask_g = (df_gastos['Fecha'].dt.date >= f_ini) & (df_gastos['Fecha'].dt.date <= f_fin)
    df_g_filtrado = df_gastos.loc[mask_g].copy()
else: df_g_filtrado = pd.DataFrame(columns=['ID', 'Fecha', 'Concepto', 'Monto'])

if not df_ventas.empty:
    st.sidebar.divider()
    st.sidebar.subheader("📂 Reportes")
    csv = convertir_df_a_csv(df_ventas)
    st.sidebar.download_button("📥 Bajar Ventas (CSV)", csv, f"Ventas_{date.today()}.csv", "text/csv")

# ALERTAS
if not df_ventas.empty:
    hoy = date.today()
    if 'Estado_Pago' in df_ventas.columns:
        pendientes = df_ventas[df_ventas['Estado_Pago'] == 'Pendiente'].copy()
        if not pendientes.empty:
            pendientes['Dias_Credito'] = pd.to_numeric(pendientes['Dias_Credito'], errors='coerce').fillna(0)
            pendientes['Vence'] = (pendientes['Fecha'] + pd.to_timedelta(pendientes['Dias_Credito'], unit='D')).dt.date
            pendientes['Dias_Restantes'] = (pendientes['Vence'] - hoy).apply(lambda x: x.days)
            urgentes = pendientes[pendientes['Dias_Restantes'] <= 3]
            if not urgentes.empty:
                st.error(f"🔔 Tienes {len(urgentes)} facturas por cobrar urgentes.")

# PESTAÑAS
tab1, tab_ana, tab_gastos, tab2, tab3 = st.tabs(["📊 Dashboard", "📈 Analítica", "💸 Gastos", "🧮 Nueva Op.", "🚦 Cartera"])

# --- TAB 1: DASHBOARD ---
with tab1:
    st.subheader("💰 Resultados Financieros")
    
    utilidad_bruta = df_v_filtrado['Utilidad'].sum() if not df_v_filtrado.empty else 0
    total_gastos = df_g_filtrado['Monto'].sum() if not df_g_filtrado.empty else 0
    utilidad_neta_real = utilidad_bruta - total_gastos
    kg_movidos = df_v_filtrado['Kg_Venta'].sum() if not df_v_filtrado.empty else 0
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Utilidad Bruta", f"${utilidad_bruta:,.0f}", delta="Operativa")
    k2.metric("Gastos Fijos", f"${total_gastos:,.0f}", delta="- Salidas", delta_color="inverse")
    k3.metric("UTILIDAD NETA", f"${utilidad_neta_real:,.0f}", delta="Bolsillo Real")
    k4.metric("Volumen (Kg)", f"{kg_movidos:,.1f} Kg")
    
    st.markdown("---")
    
    g1, g2 = st.columns(2)
    with g1:
        st.caption("Balance General")
        datos_bal = pd.DataFrame({
            'Concepto': ['Utilidad Operativa', 'Gastos Fijos', 'Utilidad Neta'],
            'Monto': [utilidad_bruta, total_gastos, utilidad_neta_real],
            'Color': ['#2196f3', '#f44336', '#4caf50']
        })
        st.plotly_chart(px.bar(datos_bal, x='Concepto', y='Monto', color='Concepto', color_discrete_map={'Utilidad Operativa': '#2196f3', 'Gastos Fijos': '#f44336', 'Utilidad Neta': '#4caf50'}), use_container_width=True)

    with g2:
        if not df_g_filtrado.empty:
            st.caption("Distribución de Gastos")
            st.plotly_chart(px.pie(df_g_filtrado, values='Monto', names='Concepto', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu), use_container_width=True)
        else:
            st.info("No hay gastos registrados en este periodo.")

# --- TAB GASTOS ---
with tab_gastos:
    st.subheader("💸 Registro de Gastos Fijos")
    with st.form("form_gasto", clear_on_submit=True):
        c_g1, c_g2, c_g3 = st.columns(3)
        fecha_g = c_g1.date_input("Fecha", date.today())
        concepto_g = c_g2.text_input("Concepto (Gasolina, Nómina...)")
        monto_g = c_g3.number_input("Valor ($)", min_value=0.0)
        
        if st.form_submit_button("🔴 Registrar Gasto"):
            if concepto_g and monto_g > 0:
                supabase.table("gastos_fijos_2026").insert({
                    "fecha": str(fecha_g), "concepto": concepto_g, "monto": monto_g
                }).execute()
                st.cache_data.clear()
                st.success("Gasto registrado")
                st.rerun()
            else: st.error("Faltan datos.")
    
    st.markdown("---")
    st.subheader("Historial de Gastos")
    if not df_g_filtrado.empty:
        st.dataframe(df_g_filtrado.style.format({"Monto": "${:,.0f}"}), use_container_width=True, hide_index=True)
        with st.expander("🗑️ Borrar Gasto"):
            id_borrar = st.number_input("ID del gasto", min_value=1, step=1)
            if st.button("Eliminar Gasto"):
                supabase.table("gastos_fijos_2026").delete().eq("id", id_borrar).execute()
                st.cache_data.clear()
                st.warning("Eliminado.")
                st.rerun()
    else: st.info("Sin gastos.")

# --- TAB ANALÍTICA ---
with tab_ana:
    st.subheader("🧠 Inteligencia de Mercado")
    if not df_v_filtrado.empty:
        df_plaza = df_v_filtrado[df_v_filtrado['Precio_Plaza'] > 0].copy()
        c_graf, c_info = st.columns([2, 1])
        with c_graf:
            if not df_plaza.empty:
                df_line = df_plaza.sort_values("Fecha")
                fig = px.line(df_line, x='Fecha', y=['Precio_Compra', 'Precio_Plaza'], markers=True, title="Histórico: Mi Compra vs Plaza")
                # Personalizar colores línea
                new_names = {'Precio_Compra': 'Mi Precio', 'Precio_Plaza': 'Precio Plaza'}
                fig.for_each_trace(lambda t: t.update(name = new_names[t.name]))
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("Faltan datos de precio plaza.")
        
        with c_info:
            if not df_plaza.empty:
                prom_c = df_plaza['Precio_Compra'].mean()
                prom_p = df_plaza['Precio_Plaza'].mean()
                diff = prom_p - prom_c
                
                st.markdown("#### Comparativa Promedio")
                st.metric("Promedio Plaza", f"${prom_p:,.0f}")
                st.metric("Mi Promedio", f"${prom_c:,.0f}")
                
                if diff > 0: st.success(f"Estás ahorrando ${diff:,.0f} por kilo vs la plaza.")
                else: st.error(f"Estás pagando ${abs(diff):,.0f} de sobrecosto vs plaza.")

# --- TAB REGISTRO ---
with tab2:
    st.subheader("📝 Nuevo Viaje")
    with st.form("registro_viaje", clear_on_submit=True):
        r1, r2, r3, r4 = st.columns(4)
        fecha_in = r1.date_input("Fecha", date.today())
        
        l_prod = obtener_opciones(df_ventas, 'Producto', ["Plátano", "Guayabo"])
        s_prod = r2.selectbox("Fruta", l_prod)
        n_prod = r2.text_input("Otra", placeholder="Si no está en lista")
        
        l_prov = obtener_opciones(df_ventas, 'Proveedor', ["Omar", "Rancho"])
        s_prov = r3.selectbox("Proveedor", l_prov)
        n_prov = r3.text_input("Otro", placeholder="Si no está en lista")

        l_cli = obtener_opciones(df_ventas, 'Cliente', ["Calima", "Fogón", "HEFE"])
        s_cli = r4.selectbox("Cliente", l_cli)
        n_cli = r4.text_input("Otro", placeholder="Si no está en lista")

        c_c, c_v = st.columns(2)
        with c_c:
            st.markdown("##### 🛒 Compra")
            kgc = st.number_input("Kg Compra", min_value=0.0)
            pc = st.number_input("Precio Compra", min_value=0.0)
            pplaza = st.number_input("Precio Plaza (Ref)", min_value=0.0)
            fl = st.number_input("Fletes", min_value=0.0)
            fec_file = st.file_uploader("Factura Compra")
        with c_v:
            st.markdown("##### 🤝 Venta")
            kgv = st.number_input("Kg Venta", min_value=0.0)
            pv = st.number_input("Precio Venta", min_value=0.0)
            desc = st.number_input("Deducciones", min_value=0.0)
            fev_file = st.file_uploader("Factura Venta")

        util_est = (kgv * pv) - (kgc * pc) - fl - desc
        st.info(f"💰 Utilidad Estimada de este viaje: **${util_est:,.0f}**")
        
        estado = st.selectbox("Estado Pago", ["Pagado", "Pendiente"])
        dias = st.number_input("Días Crédito", 8)

        if st.form_submit_button("💾 Guardar Operación"):
            fin_prod = n_prod if n_prod else s_prod
            fin_prov = n_prov if n_prov else s_prov
            fin_cli = n_cli if n_cli else s_cli
            if fin_prov and fin_cli:
                with st.spinner("Subiendo datos..."):
                    uc = subir_archivo(fec_file, f"compra_{fin_prov}")
                    uv = subir_archivo(fev_file, f"venta_{fin_cli}")
                    data = {
                        "fecha": str(fecha_in), "producto": fin_prod, "proveedor": fin_prov, "cliente": fin_cli,
                        "kg_compra": kgc, "precio_compra": pc, "fletes": fl, "viaticos": 0, "otros_gastos": 0,
                        "kg_venta": kgv, "precio_venta": pv, "retenciones": 0, "descuentos": desc,
                        "utilidad": util_est, "estado_pago": estado, "dias_credito": dias,
                        "precio_plaza": pplaza, "fec_doc_url": uc if uc else "", "fev_doc_url": uv if uv else ""
                    }
                    supabase.table("ventas_2026").insert(data).execute()
                    st.cache_data.clear()
                    st.success("Guardado Exitosamente")
                    st.rerun()

# --- TAB CARTERA ---
with tab3:
    st.subheader("📋 Historial y Cartera")
    if not df_v_filtrado.empty:
        col_cfg = {
            "FEC_Doc": st.column_config.LinkColumn("F.C", display_text="📄"),
            "FEV_Doc": st.column_config.LinkColumn("F.V", display_text="📄"),
            "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "Utilidad": st.column_config.NumberColumn("Utilidad", format="$%d"),
        }
        event = st.dataframe(df_v_filtrado.style.apply(color_deuda, axis=1), use_container_width=True, column_config=col_cfg, selection_mode="single-row", on_select="rerun", hide_index=True)
        
        if event.selection.rows:
            row = df_v_filtrado.iloc[event.selection.rows[0]]
            st.divider()
            with st.form("edit"):
                st.markdown(f"**Editando:** {row['Cliente']} ({row['Fecha'].date()})")
                c1, c2, c3, c4 = st.columns(4)
                ekc = c1.number_input("KgC", value=float(row['Kg_Compra']))
                epc = c2.number_input("PreC", value=float(row['Precio_Compra']))
                epp = c3.number_input("Plaza", value=float(row['Precio_Plaza']))
                ekv = c4.number_input("KgV", value=float(row['Kg_Venta']))
                c5, c6 = st.columns(2)
                epv = c5.number_input("PreV", value=float(row['Precio_Venta']))
                eest = c6.selectbox("Est", ["Pagado", "Pendiente"], index=0 if row['Estado_Pago'] == "Pagado" else 1)
                
                if st.form_submit_button("💾 Actualizar"):
                    gastos = row['Fletes'] + row['Descuentos']
                    n_util = (ekv * epv) - (ekc * epc) - gastos
                    supabase.table("ventas_2026").update({
                        "kg_compra": ekc, "precio_compra": epc, "kg_venta": ekv, "precio_venta": epv,
                        "precio_plaza": epp, "estado_pago": eest, "utilidad": n_util
                    }).eq("id", int(row['ID'])).execute()
                    st.cache_data.clear()
                    st.rerun()
            if st.button("🗑️ Borrar"):
                supabase.table("ventas_2026").delete().eq("id", int(row['ID'])).execute()
                st.cache_data.clear()
                st.rerun()














