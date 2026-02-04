import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta, datetime
from supabase import create_client
import io
import re
import unicodedata

# --- 1. CONFIGURACIÓN E INYECCIÓN CSS ---
st.set_page_config(page_title="Agrícola Montserrat", layout="wide", page_icon="🍌")

st.markdown("""
    <style>
    .stApp { background-color: #f8fcf8; }
    h1, h2, h3 { color: #1b5e20 !important; font-family: 'Helvetica Neue', sans-serif; }
    div[data-testid="stMetric"] {
        background-color: #ffffff; border: 1px solid #c8e6c9;
        padding: 15px; border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05); text-align: center;
    }
    div[data-testid="stMetricLabel"] { color: #388e3c; font-weight: bold; }
    .stButton>button {
        background-color: #2e7d32; color: white; border-radius: 8px; border: none;
        padding: 10px 20px; font-weight: bold;
    }
    .stButton>button:hover { background-color: #1b5e20; color: white; }
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e0e0e0; }
    </style>
""", unsafe_allow_html=True)

# --- SEGURIDAD ---
def check_password():
    if st.session_state.get("password_input") == st.secrets["APP_PASSWORD"]:
        st.session_state["password_correct"] = True
        del st.session_state["password_input"]
    else: st.error("😕 Clave incorrecta.")

if not st.session_state.get("password_correct", False):
    st.title("🔐 Acceso Restringido")
    st.text_input("Ingresa la clave maestra:", type="password", key="password_input", on_change=check_password)
    st.stop()

# --- CONEXIÓN SUPABASE ---
try:
    supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    BUCKET_FACTURAS = "facturas"
except:
    st.error("⚠️ Error de conexión.")
    st.stop()

# --- FUNCIONES ---

def limpiar_nombre(nombre):
    nombre = unicodedata.normalize('NFKD', nombre).encode('ASCII', 'ignore').decode('utf-8')
    nombre = nombre.replace(" ", "_")
    return re.sub(r'[^\w.-]', '', nombre)

def subir_archivo(archivo, nombre_base):
    if archivo:
        try:
            ext = archivo.name.split('.')[-1]
            path = f"{limpiar_nombre(nombre_base)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
            supabase.storage.from_(BUCKET_FACTURAS).upload(path, archivo.getvalue(), {"content-type": archivo.type, "upsert": "true"})
            return supabase.storage.from_(BUCKET_FACTURAS).get_public_url(path)
        except: return None
    return None

@st.cache_data(ttl=5) 
def cargar_datos():
    # 1. Ventas
    df_v = pd.DataFrame()
    try:
        res = supabase.table("ventas_2026").select("*").order("fecha", desc=True).execute()
        df_v = pd.DataFrame(res.data)
        if not df_v.empty:
            cols = {
                'id': 'ID', 'fecha': 'Fecha', 'producto': 'Producto', 'proveedor': 'Proveedor', 
                'cliente': 'Cliente', 'fec_doc_url': 'FEC_Doc', 'fev_doc_url': 'FEV_Doc', 
                'kg_compra': 'Kg_Compra', 'precio_compra': 'Precio_Compra', 'fletes': 'Fletes',
                'kg_venta': 'Kg_Venta', 'precio_venta': 'Precio_Venta', 'descuentos': 'Descuentos',
                'utilidad': 'Utilidad', 'estado_pago': 'Estado_Pago', 'dias_credito': 'Dias_Credito',
                'precio_plaza': 'Precio_Plaza'
            }
            df_v = df_v.rename(columns={k: v for k, v in cols.items() if k in df_v.columns})
            df_v['Fecha'] = pd.to_datetime(df_v['Fecha'])
            # Asegurar columnas numéricas
            for c in ['Kg_Compra','Precio_Compra','Fletes','Kg_Venta','Precio_Venta','Descuentos','Utilidad','Precio_Plaza']:
                if c in df_v.columns: df_v[c] = pd.to_numeric(df_v[c]).fillna(0.0)
    except: pass

    # 2. Gastos
    df_g = pd.DataFrame()
    try:
        res_g = supabase.table("gastos_fijos_2026").select("*").order("fecha", desc=True).execute()
        df_g = pd.DataFrame(res_g.data)
        if not df_g.empty:
            df_g = df_g.rename(columns={'id': 'ID', 'fecha': 'Fecha', 'concepto': 'Concepto', 'monto': 'Monto'})
            df_g['Fecha'] = pd.to_datetime(df_g['Fecha'])
            df_g['Monto'] = pd.to_numeric(df_g['Monto']).fillna(0.0)
    except: pass

    # 3. Saldo Inicial
    saldo_ini = 0.0
    try:
        res_c = supabase.table("configuracion_caja").select("saldo_inicial").limit(1).execute()
        if res_c.data: saldo_ini = float(res_c.data[0]['saldo_inicial'])
    except: pass

    return df_v, df_g, saldo_ini

def color_deuda(row):
    color = ''
    try:
        if row['Estado_Pago'] == 'Pagado': color = 'background-color: #e8f5e9; color: #1b5e20; font-weight: bold;'
        elif row['Estado_Pago'] == 'Pendiente':
            dias = int(row['Dias_Credito']) if pd.notnull(row['Dias_Credito']) else 0
            # Aquí usamos conversión python simple que es segura fila por fila
            vence = row['Fecha'] + timedelta(days=dias)
            if (vence.date() - date.today()).days < 0: color = 'background-color: #ffebee; color: #b71c1c; font-weight: bold;'
            elif (vence.date() - date.today()).days <= 3: color = 'background-color: #fff8e1; color: #f57f17; font-weight: bold;'
    except: pass
    return [color] * len(row)

def obtener_opciones(df, col, defaults):
    existentes = df[col].unique().tolist() if not df.empty and col in df.columns else []
    return sorted(list(set(defaults + [x for x in existentes if x])))

# --- INTERFAZ ---
st.markdown("# 🍌 Agrícola Montserrat")
st.markdown("### _Sistema de Gestión Integral 2026_")
st.divider()

# SIDEBAR
st.sidebar.title("Menú")
if st.sidebar.button("🔄 Actualizar Datos"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.divider()
f_ini = st.sidebar.date_input("📅 Inicio", date(2026, 1, 1))
f_fin = st.sidebar.date_input("📅 Fin", date(2026, 12, 31))

# CARGA DE DATOS
df_v, df_g, saldo_inicial = cargar_datos()

# CONFIGURACIÓN CAJA
st.sidebar.divider()
st.sidebar.subheader("💰 Configuración Caja")
with st.sidebar.form("config_caja"):
    nuevo_saldo = st.number_input("Saldo Inicial (Base)", value=float(saldo_inicial), format="%.2f")
    if st.form_submit_button("Actualizar Base"):
        supabase.table("configuracion_caja").update({"saldo_inicial": nuevo_saldo}).gt("id", 0).execute()
        st.cache_data.clear()
        st.rerun()

# CÁLCULO DE CAJA REAL
caja_real = saldo_inicial
ingresos_caja = 0
egresos_caja = 0

if not df_v.empty:
    ventas_pagadas = df_v[df_v['Estado_Pago'] == 'Pagado']
    ingresos_caja = (ventas_pagadas['Kg_Venta'] * ventas_pagadas['Precio_Venta']).sum()
    
    compras_total = (df_v['Kg_Compra'] * df_v['Precio_Compra']).sum()
    fletes_total = df_v['Fletes'].sum()
    egresos_caja += compras_total + fletes_total

if not df_g.empty:
    egresos_caja += df_g['Monto'].sum()

caja_real = saldo_inicial + ingresos_caja - egresos_caja

# FILTROS
df_vf = df_v[(df_v['Fecha'].dt.date >= f_ini) & (df_v['Fecha'].dt.date <= f_fin)].copy() if not df_v.empty else pd.DataFrame()
df_gf = df_g[(df_g['Fecha'].dt.date >= f_ini) & (df_g['Fecha'].dt.date <= f_fin)].copy() if not df_g.empty else pd.DataFrame(columns=['ID','Fecha','Concepto','Monto'])

# --- CORRECCIÓN: ALERTAS (LÓGICA VECTORIZADA SEGURA) ---
if not df_v.empty:
    pend = df_v[df_v['Estado_Pago'] == 'Pendiente'].copy()
    if not pend.empty:
        # Aseguramos tipo numérico para días
        pend['Dias_Credito'] = pd.to_numeric(pend['Dias_Credito'], errors='coerce').fillna(0)
        # Sumamos días usando pd.to_timedelta (formato pandas)
        pend['Vence'] = pend['Fecha'] + pd.to_timedelta(pend['Dias_Credito'], unit='D')
        
        # Fecha de referencia hoy (normalizada a medianoche para evitar error de horas)
        hoy_ts = pd.Timestamp.now().normalize()
        
        # Resta directa entre Timestamps (pandas) -> Timedelta
        # Luego extraemos .dt.days sin problemas
        mask_urg = (pend['Vence'] - hoy_ts).dt.days <= 3
        urg = pend[mask_urg]
        
        if not urg.empty: st.error(f"🔔 Tienes {len(urg)} facturas críticas por cobrar.")

# PESTAÑAS
t1, t_ana, t_gas, t2, t3 = st.tabs(["📊 Dashboard", "📈 Analítica", "💸 Gastos", "🧮 Nueva Op.", "🚦 Cartera (Editar)"])

# --- DASHBOARD ---
with t1:
    st.subheader("Estado Financiero")
    ub = df_vf['Utilidad'].sum() if not df_vf.empty else 0
    vol = df_vf['Kg_Venta'].sum() if not df_vf.empty else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("💰 CAJA REAL (DISPONIBLE)", f"${caja_real:,.0f}", delta="Efectivo en mano")
    c2.metric("Utilidad Periodo", f"${ub:,.0f}", delta="Rentabilidad")
    c3.metric("Volumen Movido", f"{vol:,.1f} Kg")
    
    st.info(f"💡 **Explicación Caja:** Base (${saldo_inicial:,.0f}) + Cobros (${ingresos_caja:,.0f}) - Pagos/Gastos (${egresos_caja:,.0f}) = **${caja_real:,.0f}**")

# --- ANALÍTICA ---
with t_ana:
    if not df_vf.empty:
        df_p = df_vf[df_vf['Precio_Plaza'] > 0].sort_values("Fecha")
        c1, c2 = st.columns([3,1])
        with c1:
            if not df_p.empty:
                st.plotly_chart(px.line(df_p, x='
















