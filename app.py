import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta, datetime
from supabase import create_client
import io

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Agrícola Montserrat 2026", layout="wide", page_icon="🍌")

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

# Usamos cache_data para velocidad, pero lo borraremos al editar/borrar
@st.cache_data(ttl=60) 
def cargar_datos():
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table("ventas_2026").select("*").order("fecha", desc=True).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            mapa_cols = {
                'id': 'ID', 
                'fecha': 'Fecha', 'producto': 'Producto', 'proveedor': 'Proveedor', 
                'cliente': 'Cliente', 'fec_doc_url': 'FEC_Doc', 'fev_doc_url': 'FEV_Doc', 
                'kg_compra': 'Kg_Compra', 'precio_compra': 'Precio_Compra', 'fletes': 'Fletes',
                'viaticos': 'Viaticos', 'otros_gastos': 'Otros_Gastos', 'kg_venta': 'Kg_Venta',
                'precio_venta': 'Precio_Venta', 'retenciones': 'Retenciones', 'descuentos': 'Descuentos',
                'utilidad': 'Utilidad', 'estado_pago': 'Estado_Pago', 'dias_credito': 'Dias_Credito'
            }
            df = df.rename(columns={k: v for k, v in mapa_cols.items() if k in df.columns})
            
            if 'Fecha' in df.columns:
                df['Fecha'] = pd.to_datetime(df['Fecha'])
            
            # Limpieza de URLs
            cols_url = ['FEC_Doc', 'FEV_Doc']
            for col in cols_url:
                if col in df.columns:
                    df[col] = df[col].replace({'': None, 'None': None, 'nan': None})
            
            return df
    except Exception as e:
        st.warning(f"Esperando datos... (Detalle: {e})")
    
    return pd.DataFrame()

def subir_archivo(archivo, nombre_base):
    if archivo and supabase:
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            nombre_clean = "".join(c for c in archivo.name if c.isalnum() or c in "._-")
            nombre_archivo = f"{nombre_base}_{timestamp}_{nombre_clean}"
            archivo_bytes = archivo.getvalue()
            
            supabase.storage.from_(BUCKET_FACTURAS).upload(
                path=nombre_archivo, 
                file=archivo_bytes, 
                file_options={"content-type": archivo.type}
            )
            return supabase.storage.from_(BUCKET_FACTURAS).get_public_url(nombre_archivo)
        except Exception as e:
            st.error(f"Error subiendo archivo: {e}")
            return None
    return None

def color_deuda(row):
    color = ''
    try:
        if row['Estado_Pago'] == 'Pagado':
            color = 'background-color: #d4edda; color: #155724;'
        elif row['Estado_Pago'] == 'Pendiente':
            dias = int(row['Dias_Credito']) if pd.notnull(row['Dias_Credito']) else 0
            vence = row['Fecha'] + timedelta(days=dias)
            dias_rest = (vence.date() - date.today()).days
            
            if dias_rest < 0: color = 'background-color: #f8d7da; color: #721c24;' 
            elif dias_rest <= 3: color = 'background-color: #fff3cd; color: #









