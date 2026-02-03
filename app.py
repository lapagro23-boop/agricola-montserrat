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

# Usamos cache con tiempo corto para velocidad, se borra al editar
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
            
            # Limpieza estricta de URLs para que Streamlit detecte los links
            cols_url = ['FEC_Doc', 'FEV_Doc']
            for col in cols_url:
                if col in df.columns:
                    # Convertimos vacíos o textos 'None' a objetos None reales
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
            
            if dias_rest < 0: 
                color = 'background-color: #f8d7da; color: #721c24;' 
            elif dias_rest <= 3: 
                color = 'background-color: #fff3cd; color: #856404;'
    except: pass
    return [color] * len(row)

def obtener_opciones(df, col, defaults):
    existentes = df[col].unique().tolist() if not df.empty and col in df.columns else []
    # Eliminamos duplicados y vacíos
    return sorted(list(set(defaults + [x for x in existentes if x])))

# --- INICIO DE LA INTERFAZ ---
st.title("🌱 Agrícola Montserrat - Gestión Global")

# SIDEBAR & FILTROS
st.sidebar.header("⚙️ Configuración")

# Botón para forzar actualización
if st.sidebar.button("🔄 Actualizar Datos"):
    st.cache_data.clear()
    st.rerun()

ver_resumen = st.sidebar.checkbox("👁️ Ver Resumen Mensual", value=(date.today().day <= 5))
st.sidebar.divider()
f_ini = st.sidebar.date_input("Inicio", date(2026, 1, 1))
f_fin = st.sidebar.date_input("Fin", date(2026, 12, 31))

df_completo = cargar_datos()

# 🔔 ZONA DE ALERTAS Y RESUMEN
if not df_completo.empty:
    hoy = date.today()
    
    # 1. Alertas de Cobro
    if 'Estado_Pago' in df_completo.columns:
        pendientes = df_completo[df_completo['Estado_Pago'] == 'Pendiente'].copy()
        if not pendientes.empty:
            pendientes['Dias_Credito'] = pd.to_numeric(pendientes['Dias_Credito'], errors='coerce').fillna(0)
            pendientes['Vence'] = (pendientes['Fecha'] + pd.to_timedelta(pendientes['Dias_Credito'], unit='D')).dt.date
            pendientes['Dias_Restantes'] = (pendientes['Vence'] - hoy).apply(lambda x: x.days)
            
            urgentes = pendientes[pendientes['Dias_Restantes'] <= 3]
            if not urgentes.empty:
                st.error(f"🔔 ¡ATENCIÓN! Tienes {len(urgentes)} facturas críticas por cobrar.")

    # 2. Resumen Mensual
    if ver_resumen:
        primer = hoy.replace(day=1)
        ultimo_anterior = primer - timedelta(days=1)
        inicio_anterior = ultimo_anterior.replace(day=1)
        
        mask_mes = (df_completo['Fecha'].dt.date >= inicio_anterior) & (df_completo['Fecha'].dt.date <= ultimo_anterior)
        df_mes = df_completo.loc[mask_mes]
        
        with st.expander(f"📅 Resumen del Mes Anterior ({ultimo_anterior.strftime('%B %Y')})", expanded=True):
            if not df_mes.empty:
                c1, c2, c3 = st.columns(3)
                util = df_mes['Utilidad'].sum()
                vta = (df_mes['Kg_Venta'] * df_mes['Precio_Venta']).sum()
                rent = (util / vta * 100) if vta > 0 else 0
                
                c1.metric("💵 Utilidad Total", f"${util:,.0f}")
                c2.metric("📦 Kg Vendidos", f"{df_mes['Kg_Venta'].sum():,.1f}")
                c3.metric("📊 Rentabilidad", f"{rent:.1f}%")
            else:
                st.info("No hubo movimientos el mes anterior.")

# FILTRO PRINCIPAL
if not df_completo.empty:
    mask = (df_completo['Fecha'].dt.date >= f_ini) & (df_completo['Fecha'].dt.date <= f_fin)
    df = df_completo.loc[mask].copy()
else:
    df = pd.DataFrame(columns=df_completo.columns)

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🧮 Nueva Operación", "🚦 Cartera & Edición"])

# --- TAB 1: DASHBOARD ---
with tab1:
    if not df.empty:
        df['Diferencia_Kg'] = df['Kg_Venta'] - df['Kg_Compra']
        merma = df[df['Diferencia_Kg'] < 0]['Diferencia_Kg'].sum()
        ganancia = df[df['Diferencia_Kg'] > 0]['Diferencia_Kg'].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Utilidad Periodo", f"${df['Utilidad'].sum():,.0f}")
        c2.metric("📦 Kg Movidos", f"{df['Kg_Venta'].sum():,.1f}")
        c3.metric("⚖️ Merma", f"{abs(merma):,.1f} Kg", delta_color="inverse")
        c4.metric("📈 Ganancia Peso", f"{ganancia:,.1f} Kg")
        
        st.plotly_chart(px.bar(df, x='Proveedor', y='Utilidad', color='Producto', title="Utilidad por Proveedor"), use_container_width=True)
    else:
        st.info("No hay datos en el rango seleccionado.")

# --- TAB 2: REGISTRO ---
with tab2:
    st.header("Registrar Viaje")
    with st.form("registro_viaje", clear_on_submit=True):
        r1, r2, r3, r4 = st.columns(4)
        fecha_in = r1.date_input("Fecha", date.today())
        
        # Desplegables con opción de escribir uno nuevo abajo
        l_prod = obtener_opciones(df_completo, 'Producto', ["Plátano", "Guayabo"])
        s










