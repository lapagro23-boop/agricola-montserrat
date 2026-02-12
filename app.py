"""
Sistema de Gestión Agrícola Montserrat - Versión Completa Final
Incluye todas las mejoras:
- Fórmula de utilidad corregida (coincide con Google Sheet)
- Dashboard mejorado con KPIs, rankings, alertas, tendencias
- Validación completa de datos
- Manejo robusto de excepciones
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta, datetime
from supabase import create_client
import io
import re
import unicodedata
import logging

# ==================== CONFIGURACIÓN ====================

logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constantes
CACHE_TTL_SECONDS = 300
DEFAULT_CREDITO_DIAS = 8
ALLOWED_FILE_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

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
    .stButton>button {
        background-color: #2e7d32; color: white; border-radius: 8px; border: none;
        padding: 10px 20px; font-weight: bold;
    }
    .stButton>button:hover { background-color: #1b5e20; color: white; }
    </style>
""", unsafe_allow_html=True)

# ==================== FUNCIONES DE VALIDACIÓN ====================

def validar_cantidad(valor, nombre_campo, permitir_cero=False):
    if valor is None:
        return False, f"{nombre_campo} no puede estar vacío"
    if not permitir_cero and valor <= 0:
        return False, f"{nombre_campo} debe ser mayor a 0"
    if permitir_cero and valor < 0:
        return False, f"{nombre_campo} no puede ser negativo"
    if valor > 1000000:
        return False, f"{nombre_campo} excede el límite permitido"
    return True, ""

def validar_operacion_comercial(kg_compra, precio_compra, kg_venta, precio_venta, 
                                viaticos, fletes, otros_gastos, retenciones, descuentos):
    errores = []
    advertencias = []
    
    validaciones = [
        (kg_compra, "Kg Compra"),
        (precio_compra, "Precio Compra"),
        (kg_venta, "Kg Venta"),
        (precio_venta, "Precio Venta"),
        (viaticos, "Viáticos", True),
        (fletes, "Fletes", True),
        (otros_gastos, "Otros Gastos", True),
        (retenciones, "Retenciones", True),
        (descuentos, "Descuentos", True)
    ]
    
    for validacion in validaciones:
        permitir_cero = validacion[2] if len(validacion) > 2 else False
        es_valido, mensaje = validar_cantidad(validacion[0], validacion[1], permitir_cero)
        if not es_valido:
            errores.append(mensaje)
    
    if errores:
        return False, advertencias, errores
    
    if kg_venta > kg_compra * 1.1:
        advertencias.append(f"⚠️ Vendes {kg_venta - kg_compra:.2f} kg más de lo que compraste.")
    
    if precio_venta < precio_compra * 0.9:
        margen = ((precio_venta - precio_compra) / precio_compra) * 100
        advertencias.append(f"⚠️ Pérdida en precio: ${precio_venta:,.0f} vs ${precio_compra:,.0f} ({margen:.1f}%)")
    
    utilidad_neta = calcular_utilidad_neta(
        kg_venta, precio_venta, kg_compra, precio_compra, 
        viaticos, fletes, otros_gastos, retenciones, descuentos
    )
    
    if utilidad_neta < 0:
        advertencias.append(f"💰 Utilidad neta negativa: ${utilidad_neta:,.0f}")
    
    return True, advertencias, errores

def validar_archivo(archivo):
    if not archivo:
        return True, ""
    
    ext = archivo.name.split('.')[-1].lower()
    if ext not in ALLOWED_FILE_EXTENSIONS:
        return False, f"Formato no permitido. Usa: {', '.join(ALLOWED_FILE_EXTENSIONS)}"
    
    archivo.seek(0, 2)
    size = archivo.tell()
    archivo.seek(0)
    
    if size > MAX_FILE_SIZE_BYTES:
        return False, f"Archivo muy grande ({size/1024/1024:.1f}MB). Máximo: {MAX_FILE_SIZE_MB}MB"
    
    return True, ""

# ==================== FUNCIONES DE NEGOCIO ====================

def calcular_utilidad_neta(kg_venta, precio_venta, kg_compra, precio_compra, 
                          viaticos, fletes, otros_gastos, retenciones, descuentos):
    costo_bruto = kg_compra * precio_compra
    costo_neto = costo_bruto + viaticos + fletes + otros_gastos
    ingreso_total = kg_venta * precio_venta
    utilidad_bruta = ingreso_total - costo_neto
    utilidad_neta = utilidad_bruta - retenciones - descuentos
    return utilidad_neta

def calcular_utilidad_bruta(kg_venta, precio_venta, kg_compra, precio_compra, 
                           viaticos, fletes, otros_gastos):
    costo_neto = (kg_compra * precio_compra) + viaticos + fletes + otros_gastos
    ingreso_total = kg_venta * precio_venta
    return ingreso_total - costo_neto

def limpiar_nombre_archivo(nombre):
    nombre = unicodedata.normalize('NFKD', nombre).encode('ASCII', 'ignore').decode('utf-8')
    nombre = re.sub(r'[^\w]', '_', nombre)
    return nombre

def color_deuda(row):
    color = ''
    try:
        if row['Estado_Pago'] == 'Pagado':
            color = 'background-color: #e8f5e9; color: #1b5e20; font-weight: bold;'
        elif row['Estado_Pago'] == 'Pendiente':
            dias_credito = int(row['Dias_Credito']) if pd.notnull(row['Dias_Credito']) else 0
            fecha_vencimiento = row['Fecha'] + timedelta(days=dias_credito)
            dias_restantes = (fecha_vencimiento.date() - date.today()).days
            
            if dias_restantes < 0:
                color = 'background-color: #ffebee; color: #b71c1c; font-weight: bold;'
            elif dias_restantes <= 3:
                color = 'background-color: #fff8e1; color: #f57f17; font-weight: bold;'
    except Exception as e:
        logger.error(f"Error al aplicar color a fila: {e}")
    
    return [color] * len(row)

def obtener_opciones(df, columna, valores_default):
    existentes = df[columna].unique().tolist() if not df.empty and columna in df.columns else []
    todas = list(set(valores_default + [x for x in existentes if x]))
    return sorted(todas)

# ==================== FUNCIONES DE BASE DE DATOS ====================

def subir_archivo(archivo, nombre_base):
    if not archivo:
        return None
    
    es_valido, mensaje_error = validar_archivo(archivo)
    if not es_valido:
        st.error(f"❌ {mensaje_error}")
        return None
    
    try:
        ext = archivo.name.split('.')[-1].lower()
        nombre_limpio = limpiar_nombre_archivo(nombre_base)
        timestamp = datetime.now().strftime('%m%d_%H%M')
        nombre_archivo = f"{nombre_limpio}_{timestamp}.{ext}"
        
        supabase.storage.from_(BUCKET_FACTURAS).upload(
            nombre_archivo,
            archivo.getvalue(),
            {"content-type": archivo.type, "upsert": "true"}
        )
        
        url_publica = supabase.storage.from_(BUCKET_FACTURAS).get_public_url(nombre_archivo)
        logger.info(f"Archivo subido exitosamente: {nombre_archivo}")
        return url_publica
        
    except Exception as e:
        logger.error(f"Error al subir archivo: {e}")
        st.error(f"❌ Error al subir archivo: {str(e)}")
        return None

@st.cache_data(ttl=CACHE_TTL_SECONDS)
def cargar_datos():
    df_ventas = pd.DataFrame()
    try:
        respuesta = supabase.table("ventas_2026").select("*").order("fecha", desc=True).execute()
        df_ventas = pd.DataFrame(respuesta.data)
        
        if not df_ventas.empty:
            columnas_mapa = {
                'id': 'ID', 'fecha': 'Fecha', 'producto': 'Producto', 
                'proveedor': 'Proveedor', 'cliente': 'Cliente',
                'fec_doc_url': 'FEC_Doc', 'fev_doc_url': 'FEV_Doc',
                'kg_compra': 'Kg_Compra', 'precio_compra': 'Precio_Compra',
                'viaticos': 'Viaticos', 'fletes': 'Fletes', 'otros_gastos': 'Otros_Gastos',
                'kg_venta': 'Kg_Venta', 'precio_venta': 'Precio_Venta',
                'retenciones': 'Retenciones', 'descuentos': 'Descuentos',
                'utilidad': 'Utilidad', 'estado_pago': 'Estado_Pago',
                'dias_credito': 'Dias_Credito', 'precio_plaza': 'Precio_Plaza'
            }
            df_ventas = df_ventas.rename(
                columns={k: v for k, v in columnas_mapa.items() if k in df_ventas.columns}
            )
            
            df_ventas['Fecha'] = pd.to_datetime(df_ventas['Fecha'])
            
            campos_numericos = [
                'Kg_Compra', 'Precio_Compra', 'Viaticos', 'Fletes', 'Otros_Gastos',
                'Kg_Venta', 'Precio_Venta', 'Retenciones', 'Descuentos', 
                'Utilidad', 'Precio_Plaza'
            ]
            for campo in campos_numericos:
                if campo in df_ventas.columns:
                    df_ventas[campo] = pd.to_numeric(df_ventas[campo], errors='coerce').fillna(0.0)
            
            for campo in ['FEC_Doc', 'FEV_Doc']:
                if campo in df_ventas.columns:
                    df_ventas[campo] = df_ventas[campo].replace({'': None, 'None': None, 'nan': None})
                    
    except Exception as e:
        logger.error(f"Error al cargar ventas: {e}")
        st.error(f"⚠️ Error al cargar ventas: {str(e)}")
    
    df_gastos = pd.DataFrame()
    try:
        respuesta_gastos = supabase.table("gastos_fijos_2026").select("*").order("fecha", desc=True).execute()
        df_gastos = pd.DataFrame(respuesta_gastos.data)
        
        if not df_gastos.empty:
            df_gastos = df_gastos.rename(columns={
                'id': 'ID', 'fecha': 'Fecha', 'concepto': 'Concepto',
                'monto': 'Monto', 'tipo': 'Tipo'
            })
            df_gastos['Fecha'] = pd.to_datetime(df_gastos['Fecha'])
            df_gastos['Monto'] = pd.to_numeric(df_gastos['Monto'], errors='coerce').fillna(0.0)
            
            if 'Tipo' not in df_gastos.columns:
                df_gastos['Tipo'] = 'Gasto'
                
    except Exception as e:
        logger.error(f"Error al cargar gastos: {e}")
        st.error(f"⚠️ Error al cargar gastos: {str(e)}")
    
    saldo_inicial = 0.0
    try:
        respuesta_config = supabase.table("configuracion_caja").select("saldo_inicial").limit(1).execute()
        if respuesta_config.data:
            saldo_inicial = float(respuesta_config.data[0]['saldo_inicial'])
    except Exception as e:
        logger.error(f"Error al cargar configuración: {e}")
        st.error(f"⚠️ Error al cargar configuración de caja: {str(e)}")
    
    return df_ventas, df_gastos, saldo_inicial

# ==================== SEGURIDAD ====================

def verificar_password():
    if st.session_state.get("password_input") == st.secrets.get("APP_PASSWORD"):
        st.session_state["password_correct"] = True
        del st.session_state["password_input"]
    else:
        st.error("😕 Clave incorrecta.")

if not st.session_state.get("password_correct", False):
    st.title("🔐 Acceso Restringido")
    st.text_input("Ingresa la clave maestra:", type="password", key="password_input", on_change=verificar_password)
    st.stop()

# ==================== CONEXIÓN A SUPABASE ====================

try:
    supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    BUCKET_FACTURAS = "facturas"
    logger.info("Conexión a Supabase establecida exitosamente")
except KeyError as e:
    logger.error(f"Falta configuración en secrets: {e}")
    st.error(f"⚠️ Error de configuración: Falta {e}")
    st.stop()
except Exception as e:
    logger.error(f"Error al conectar con Supabase: {e}")
    st.error(f"⚠️ Error de conexión: {str(e)}")
    st.stop()

# ==================== INTERFAZ PRINCIPAL ====================

st.markdown("# 🍌 Agrícola Montserrat")
st.markdown("### _Sistema de Gestión Integral 2026_")
st.divider()

st.sidebar.title("Menú")
if st.sidebar.button("🔄 Actualizar Datos"):
    cargar_datos.clear()
    st.rerun()

st.sidebar.divider()

fecha_inicio = st.sidebar.date_input("📅 Inicio", date(2026, 1, 1))
fecha_fin = st.sidebar.date_input("📅 Fin", date(2026, 12, 31))

df_ventas, df_gastos, saldo_inicial = cargar_datos()

# ==================== CÁLCULOS FINANCIEROS ====================

ingresos_caja = 0.0
egresos_caja = 0.0

if not df_ventas.empty:
    ventas_pagadas = df_ventas[df_ventas['Estado_Pago'] == 'Pagado']
    ingresos_caja += (ventas_pagadas['Kg_Venta'] * ventas_pagadas['Precio_Venta']).sum()
    
    costo_bruto = (df_ventas['Kg_Compra'] * df_ventas['Precio_Compra']).sum()
    viaticos_total = df_ventas['Viaticos'].sum() if 'Viaticos' in df_ventas.columns else 0
    fletes_total = df_ventas['Fletes'].sum()
    otros_total = df_ventas['Otros_Gastos'].sum() if 'Otros_Gastos' in df_ventas.columns else 0
    egresos_caja += costo_bruto + viaticos_total + fletes_total + otros_total

if not df_gastos.empty:
    gastos_operativos = df_gastos[df_gastos['Tipo'] == 'Gasto']
    egresos_caja += gastos_operativos['Monto'].sum()
    
    prestamos_salida = df_gastos[df_gastos['Tipo'] == 'Préstamo Salida']
    egresos_caja += prestamos_salida['Monto'].sum()
    
    ingresos_extra = df_gastos[df_gastos['Tipo'] == 'Ingreso Extra']
    ingresos_caja += ingresos_extra['Monto'].sum()

flujo_acumulado = ingresos_caja - egresos_caja
caja_sistema = saldo_inicial + flujo_acumulado

# ==================== CALIBRACIÓN DE CAJA ====================

st.sidebar.divider()
st.sidebar.subheader("💰 Calibrar Caja")

with st.sidebar.form("config_caja"):
    st.caption(f"Sistema: ${caja_sistema:,.0f}")
    valor_real = st.number_input("Realidad HOY:", value=float(caja_sistema), format="%.2f")
    
    if st.form_submit_button("✅ Ajustar"):
        try:
            nueva_base = valor_real - flujo_acumulado
            supabase.table("configuracion_caja").update({"saldo_inicial": nueva_base}).gt("id", 0).execute()
            cargar_datos.clear()
            st.success("✅ Caja ajustada exitosamente")
            st.rerun()
        except Exception as e:
            logger.error(f"Error al ajustar caja: {e}")
            st.error(f"❌ Error al ajustar: {str(e)}")

# ==================== FILTROS ====================

df_ventas_filtradas = df_ventas[
    (df_ventas['Fecha'].dt.date >= fecha_inicio) &
    (df_ventas['Fecha'].dt.date <= fecha_fin)
].copy() if not df_ventas.empty else pd.DataFrame()

df_gastos_filtrados = df_gastos[
    (df_gastos['Fecha'].dt.date >= fecha_inicio) &
    (df_gastos['Fecha'].dt.date <= fecha_fin)
].copy() if not df_gastos.empty else pd.DataFrame(columns=['ID', 'Fecha', 'Concepto', 'Monto', 'Tipo'])

# ==================== ALERTAS ====================

if not df_ventas.empty:
    pendientes = df_ventas[df_ventas['Estado_Pago'] == 'Pendiente'].copy()
    
    if not pendientes.empty:
        pendientes['Dias_Credito'] = pd.to_numeric(pendientes['Dias_Credito'], errors='coerce').fillna(0)
        pendientes['Vence'] = pendientes['Fecha'] + pd.to_timedelta(pendientes['Dias_Credito'], unit='D')
        
        hoy = pd.Timestamp.now().normalize()
        dias_hasta_vencimiento = (pendientes['Vence'] - hoy).dt.days
        
        urgentes = pendientes[dias_hasta_vencimiento <= 3]
        if not urgentes.empty:
            st.error(f"🔔 Tienes {len(urgentes)} factura(s) crítica(s) por cobrar.")

# ==================== PESTAÑAS ====================

tab_dashboard, tab_analitica, tab_movimientos, tab_nueva_op, tab_cartera = st.tabs([
    "📊 Dashboard",
    "📈 Analítica",
    "💸 Movimientos",
    "🧮 Nueva Op.",
    "🚦 Cartera"
])

# ==================== TAB: DASHBOARD ====================

with tab_dashboard:
    st.subheader("Estado Financiero")
    
    utilidad_operaciones = df_ventas_filtradas['Utilidad'].sum() if not df_ventas_filtradas.empty else 0
    gastos_periodo = df_gastos_filtrados[df_gastos_filtrados['Tipo'] == 'Gasto']['Monto'].sum() \
        if not df_gastos_filtrados.empty else 0
    utilidad_neta_final = utilidad_operaciones - gastos_periodo
    volumen_total = df_ventas_filtradas['Kg_Venta'].sum() if not df_ventas_filtradas.empty else 0
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 CAJA REAL", f"${caja_sistema:,.0f}", delta="Disponible")
    col2.metric("📦 Utilidad Operaciones", f"${utilidad_operaciones:,.0f}", delta="Sin gastos fijos")
    col3.metric("💵 Utilidad Neta", f"${utilidad_neta_final:,.0f}", delta="Después de gastos")
    col4.metric("📊 Volumen", f"{volumen_total:,.1f} Kg")
    
    if gastos_periodo > 0:
        st.divider()
        st.markdown("### 📋 Desglose de Gastos Fijos")
        
        col_a, col_b = st.columns([2, 1])
        
        with col_a:
            if not df_gastos_filtrados.empty:
                gastos_detalle = df_gastos_filtrados[df_gastos_filtrados['Tipo'] == 'Gasto'][
                    ['Fecha', 'Concepto', 'Monto']
                ].copy()
                
                if not gastos_detalle.empty:
                    st.dataframe(
                        gastos_detalle.style.format({'Monto': '${:,.0f}'}),
                        use_container_width=True,
                        hide_index=True
                    )
        
        with col_b:
            st.metric("Total Gastos Fijos", f"${gastos_periodo:,.0f}", 
                     delta=f"-{(gastos_periodo/utilidad_operaciones*100):.1f}% de utilidad" if utilidad_operaciones > 0 else "")
            
            if utilidad_operaciones > 0:
                margen = (utilidad_neta_final / utilidad_operaciones) * 100
                st.metric("Margen Neto", f"{margen:.1f}%", delta="Después de gastos fijos")
    
    st.divider()
    
    # KPIs
    st.markdown("### 📊 KPIs de Rendimiento")
    
    if not df_ventas_filtradas.empty:
        num_operaciones = len(df_ventas_filtradas)
        utilidad_promedio_op = utilidad_operaciones / num_operaciones if num_operaciones > 0 else 0
        kg_promedio_op = volumen_total / num_operaciones if num_operaciones > 0 else 0
        margen_promedio = (df_ventas_filtradas['Precio_Venta'] - df_ventas_filtradas['Precio_Compra']).mean()
        
        if len(df_ventas_filtradas) > 1:
            dias_operacion = (df_ventas_filtradas['Fecha'].max() - df_ventas_filtradas['Fecha'].min()).days + 1
            operaciones_por_dia = num_operaciones / dias_operacion if dias_operacion > 0 else 0
        else:
            dias_operacion = 1
            operaciones_por_dia = num_operaciones
        
        col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
        
        with col_kpi1:
            st.metric("Utilidad/Operación", f"${utilidad_promedio_op:,.0f}", help="Promedio de ganancia por viaje")
        with col_kpi2:
            st.metric("Kg/Operación", f"{kg_promedio_op:,.0f} kg", help="Volumen promedio por viaje")
        with col_kpi3:
            st.metric("Margen Unitario", f"${margen_promedio:,.0f}/kg", help="Diferencia promedio precio venta - compra")
        with col_kpi4:
            st.metric("Operaciones/Día", f"{operaciones_por_dia:.1f}", help=f"{num_operaciones} operaciones en {dias_operacion} días")
    
    st.divider()
    
    # Rankings
    st.markdown("### 🏆 Rankings del Periodo")
    
    if not df_ventas_filtradas.empty:
        col_rank1, col_rank2 = st.columns(2)
        
        with col_rank1:
            st.markdown("**🤝 Mejores Clientes**")
            
            clientes_stats = df_ventas_filtradas.groupby('Cliente').agg({
                'Utilidad': 'sum',
                'Kg_Venta': 'sum',
                'ID': 'count'
            }).rename(columns={'ID': 'Operaciones'}).sort_values('Utilidad', ascending=False)
            
            clientes_stats['% Total'] = (clientes_stats['Utilidad'] / utilidad_operaciones * 100).round(1)
            
            clientes_display = clientes_stats.copy()
            clientes_display['Utilidad'] = clientes_display['Utilidad'].apply(lambda x: f"${x:,.0f}")
            clientes_display['Kg_Venta'] = clientes_display['Kg_Venta'].apply(lambda x: f"{x:,.0f} kg")
            clientes_display['% Total'] = clientes_display['% Total'].apply(lambda x: f"{x}%")
            
            st.dataframe(clientes_display[['Utilidad', 'Operaciones', '% Total']], use_container_width=True)
        
        with col_rank2:
            st.markdown("**🚚 Mejores Proveedores**")
            
            proveedores_stats = df_ventas_filtradas.groupby('Proveedor').agg({
                'Utilidad': 'sum',
                'Kg_Compra': 'sum',
                'Precio_Compra': 'mean',
                'ID': 'count'
            }).rename(columns={'ID': 'Operaciones'}).sort_values('Utilidad', ascending=False)
            
            proveedores_display = proveedores_stats.copy()
            proveedores_display['Utilidad'] = proveedores_display['Utilidad'].apply(lambda x: f"${x:,.0f}")
            proveedores_display['Precio_Compra'] = proveedores_display['Precio_Compra'].apply(lambda x: f"${x:,.0f}/kg")
            
            st.dataframe(proveedores_display[['Utilidad', 'Operaciones', 'Precio_Compra']], use_container_width=True)
    
    st.divider()
    
    # Alertas y Recomendaciones
    st.markdown("### 🚨 Alertas y Recomendaciones")
    
    alertas = []
    recomendaciones = []
    
    if not df_ventas_filtradas.empty:
        operaciones_perdida = df_ventas_filtradas[df_ventas_filtradas['Utilidad'] < 0]
        if not operaciones_perdida.empty:
            total_perdida = operaciones_perdida['Utilidad'].sum()
            alertas.append({
                'tipo': 'warning',
                'mensaje': f"⚠️ {len(operaciones_perdida)} operación(es) con pérdida: ${abs(total_perdida):,.0f}"
            })
        
        if not clientes_stats.empty:
            principal_cliente = clientes_stats.iloc[0]
            if principal_cliente['% Total'] > 40:
                alertas.append({
                    'tipo': 'info',
                    'mensaje': f"ℹ️ {principal_cliente.name} representa {principal_cliente['% Total']}% de utilidad (riesgo de concentración)"
                })
        
        operaciones_margen_bajo = df_ventas_filtradas[
            (df_ventas_filtradas['Precio_Venta'] - df_ventas_filtradas['Precio_Compra']) < 300
        ]
        if not operaciones_margen_bajo.empty:
            alertas.append({
                'tipo': 'warning',
                'mensaje': f"⚠️ {len(operaciones_margen_bajo)} operación(es) con margen <$300/kg"
            })
        
        if not proveedores_stats.empty and len(proveedores_stats) > 1:
            mejor_prov_idx = proveedores_stats['Precio_Compra'].idxmin()
            peor_prov_idx = proveedores_stats['Precio_Compra'].idxmax()
            
            precio_mejor = proveedores_stats.loc[mejor_prov_idx, 'Precio_Compra']
            precio_peor = proveedores_stats.loc[peor_prov_idx, 'Precio_Compra']
            
            if precio_peor > precio_mejor * 1.1:
                kg_peor = proveedores_stats.loc[peor_prov_idx, 'Kg_Compra']
                ahorro_potencial = (precio_peor - precio_mejor) * kg_peor
                recomendaciones.append({
                    'tipo': 'success',
                    'mensaje': f"💡 Comprar más a {mejor_prov_idx} en vez de {peor_prov_idx} ahorraría ~${ahorro_potencial:,.0f}"
                })
    
    if alertas or recomendaciones:
        col_alert, col_recom = st.columns(2)
        
        with col_alert:
            if alertas:
                for alerta in alertas:
                    if alerta['tipo'] == 'warning':
                        st.warning(alerta['mensaje'])
                    else:
                        st.info(alerta['mensaje'])
        
        with col_recom:
            if recomendaciones:
                for rec in recomendaciones:
                    if rec['tipo'] == 'success':
                        st.success(rec['mensaje'])
                    else:
                        st.info(rec['mensaje'])
    else:
        st.info("✅ Todo se ve bien. No hay alertas en este momento.")
    
    st.divider()
    
    # Tendencias
    st.markdown("### 📈 Tendencias y Proyecciones")
    
    if not df_ventas_filtradas.empty and len(df_ventas_filtradas) >= 5:
        tendencias = df_ventas_filtradas.groupby(df_ventas_filtradas['Fecha'].dt.date).agg({
            'Utilidad': 'sum',
            'Kg_Venta': 'sum'
        }).reset_index()
        tendencias.columns = ['Fecha', 'Utilidad', 'Kg_Venta']
        
        if len(tendencias) > 7:
            tendencias['Utilidad_MA7'] = tendencias['Utilidad'].rolling(window=7, min_periods=1).mean()
        
        fig = make_subplots(rows=1, cols=2, subplot_titles=('Utilidad Diaria', 'Volumen Diario'))
        
        fig.add_trace(
            go.Bar(x=tendencias['Fecha'], y=tendencias['Utilidad'], name='Utilidad Diaria', marker_color='lightgreen'),
            row=1, col=1
        )
        
        if 'Utilidad_MA7' in tendencias.columns:
            fig.add_trace(
                go.Scatter(x=tendencias['Fecha'], y=tendencias['Utilidad_MA7'], 
                          name='Promedio 7 días', line=dict(color='darkgreen', width=2)),
                row=1, col=1
            )
        
        fig.add_trace(
            go.Bar(x=tendencias['Fecha'], y=tendencias['Kg_Venta'], name='Kg Vendidos',
                   marker_color='lightblue', showlegend=False),
            row=1, col=2
        )
        
        fig.update_xaxes(title_text="Fecha", row=1, col=1)
        fig.update_xaxes(title_text="Fecha", row=1, col=2)
        fig.update_yaxes(title_text="Utilidad ($)", row=1, col=1)
        fig.update_yaxes(title_text="Kg", row=1, col=2)
        fig.update_layout(height=400, showlegend=True)
        
        st.plotly_chart(fig, use_container_width=True)
        
        if len(tendencias) >= 7:
            promedio_diario = tendencias['Utilidad'].tail(7).mean()
            dias_restantes_mes = 30 - len(tendencias)
            
            if dias_restantes_mes > 0:
                proyeccion_mes = utilidad_operaciones + (promedio_diario * dias_restantes_mes)
                
                col_proy1, col_proy2 = st.columns(2)
                with col_proy1:
                    st.metric("Proyección Fin de Mes", f"${proyeccion_mes:,.0f}",
                             delta=f"+${promedio_diario * dias_restantes_mes:,.0f} estimado",
                             help=f"Basado en promedio de últimos 7 días (${promedio_diario:,.0f}/día)")
                
                with col_proy2:
                    if utilidad_operaciones > 0:
                        porcentaje_avance = (utilidad_operaciones / proyeccion_mes * 100)
                        st.metric("Avance del Mes", f"{porcentaje_avance:.1f}%",
                                 help=f"Llevas ${utilidad_operaciones:,.0f} de ${proyeccion_mes:,.0f} proyectado")
    
    st.divider()
    
    # Comparativa Productos
    st.markdown("### 📊 Comparativa de Productos")
    
    if not df_ventas_filtradas.empty and 'Producto' in df_ventas_filtradas.columns:
        productos_stats = df_ventas_filtradas.groupby('Producto').agg({
            'Utilidad': 'sum',
            'Kg_Venta': 'sum',
            'ID': 'count'
        }).rename(columns={'ID': 'Operaciones'}).sort_values('Utilidad', ascending=False)
        
        if not productos_stats.empty and len(productos_stats) > 1:
            productos_stats['Utilidad_por_Kg'] = productos_stats['Utilidad'] / productos_stats['Kg_Venta']
            
            col_prod1, col_prod2 = st.columns(2)
            
            with col_prod1:
                fig_productos = go.Figure(data=[
                    go.Bar(
                        x=productos_stats.index,
                        y=productos_stats['Utilidad'],
                        text=productos_stats['Utilidad'].apply(lambda x: f"${x:,.0f}"),
                        textposition='auto',
                        marker_color=['#2e7d32' if i == 0 else '#66bb6a' for i in range(len(productos_stats))]
                    )
                ])
                fig_productos.update_layout(
                    title="Utilidad Total por Producto",
                    xaxis_title="Producto",
                    yaxis_title="Utilidad ($)",
                    showlegend=False,
                    height=300
                )
                st.plotly_chart(fig_productos, use_container_width=True)
            
            with col_prod2:
                fig_rentabilidad = go.Figure(data=[
                    go.Bar(
                        x=productos_stats.index,
                        y=productos_stats['Utilidad_por_Kg'],
                        text=productos_stats['Utilidad_por_Kg'].apply(lambda x: f"${x:,.0f}/kg"),
                        textposition='auto',
                        marker_color=['#1565c0' if i == 0 else '#42a5f5' for i in range(len(productos_stats))]
                    )
                ])
                fig_rentabilidad.update_layout(
                    title="Rentabilidad por Kg",
                    xaxis_title="Producto",
                    yaxis_title="Utilidad por Kg ($/kg)",
                    showlegend=False,
                    height=300
                )
                st.plotly_chart(fig_rentabilidad, use_container_width=True)

# ==================== TAB: ANALÍTICA ====================

with tab_analitica:
    st.subheader("📈 Análisis Financiero")
    
    st.markdown("### 💰 Flujo de Utilidades")
    
    if not df_ventas_filtradas.empty:
        col_flow1, col_flow2, col_flow3 = st.columns(3)
        
        utilidad_ops = df_ventas_filtradas['Utilidad'].sum()
        gastos_fijos_total = df_gastos_filtrados[df_gastos_filtrados['Tipo'] == 'Gasto']['Monto'].sum() \
            if not df_gastos_filtrados.empty else 0
        utilidad_final = utilidad_ops - gastos_fijos_total
        
        with col_flow1:
            st.metric("1️⃣ Utilidad Operaciones", f"${utilidad_ops:,.0f}",
                     help="Ganancia de las operaciones comerciales (ventas - costos)")
        
        with col_flow2:
            st.metric("2️⃣ Gastos Fijos", f"-${gastos_fijos_total:,.0f}",
                     delta=f"{(gastos_fijos_total/utilidad_ops*100):.1f}% de utilidad" if utilidad_ops > 0 else "",
                     delta_color="inverse",
                     help="Nómina, gasolina, y otros gastos operativos fijos")
        
        with col_flow3:
            st.metric("3️⃣ Utilidad Neta Final", f"${utilidad_final:,.0f}",
                     delta=f"{(utilidad_final/utilidad_ops*100):.1f}% margen" if utilidad_ops > 0 else "",
                     help="Ganancia real después de todos los gastos")
        
        fig_waterfall = go.Figure(go.Waterfall(
            name="Flujo de Utilidad",
            orientation="v",
            measure=["relative", "relative", "total"],
            x=["Utilidad<br>Operaciones", "Gastos<br>Fijos", "Utilidad<br>Neta"],
            y=[utilidad_ops, -gastos_fijos_total, utilidad_final],
            text=[f"${utilidad_ops:,.0f}", f"-${gastos_fijos_total:,.0f}", f"${utilidad_final:,.0f}"],
            textposition="outside",
            connector={"line":{"color":"rgb(63, 63, 63)"}},
        ))
        
        fig_waterfall.update_layout(title="Flujo de Utilidad", showlegend=False, height=400)
        st.plotly_chart(fig_waterfall, use_container_width=True)
        
        st.divider()
    
    st.markdown("### 📊 Análisis de Precios")
    
    if not df_ventas_filtradas.empty:
        df_precios = df_ventas_filtradas[df_ventas_filtradas['Precio_Plaza'] > 0].sort_values("Fecha")
        
        col_grafico, col_metrica = st.columns([3, 1])
        
        with col_grafico:
            if not df_precios.empty:
                fig = px.line(df_precios, x='Fecha', y=['Precio_Compra', 'Precio_Plaza'],
                             markers=True, title="Evolución: Precio Compra vs Plaza")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Faltan datos de precio de plaza.")
        
        with col_metrica:
            if not df_precios.empty:
                precio_plaza_promedio = df_precios['Precio_Plaza'].mean()
                precio_compra_promedio = df_precios['Precio_Compra'].mean()
                ahorro_promedio = precio_plaza_promedio - precio_compra_promedio
                
                st.metric("Margen vs Plaza", f"${ahorro_promedio:,.0f}",
                         delta="Ahorro/Kg" if ahorro_promedio > 0 else "Sobrecosto")
                
                if ahorro_promedio > 0:
                    ahorro_total = ahorro_promedio * df_precios['Kg_Compra'].sum()
                    st.metric("Ahorro Total", f"${ahorro_total:,.0f}",
                             help="Si hubieras comprado al precio de plaza")

# ==================== TAB: MOVIMIENTOS ====================

with tab_movimientos:
    st.subheader("💸 Registro de Movimientos")
    
    with st.form("add_movimiento", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns(4)
        
        fecha_mov = col1.date_input("Fecha", date.today())
        concepto_mov = col2.text_input("Concepto")
        tipo_mov = col3.selectbox("Tipo", ["Gasto (Gasolina/Nómina)", "Préstamo Salida", "Ingreso Extra"])
        monto_mov = col4.number_input("Valor ($)", min_value=0.0, format="%.2f")
        
        if st.form_submit_button("Registrar"):
            tipo_db = "Gasto"
            if "Préstamo" in tipo_mov:
                tipo_db = "Préstamo Salida"
            elif "Ingreso" in tipo_mov:
                tipo_db = "Ingreso Extra"
            
            if not concepto_mov:
                st.error("❌ El concepto es obligatorio")
            elif monto_mov <= 0:
                st.error("❌ El monto debe ser mayor a 0")
            else:
                try:
                    supabase.table("gastos_fijos_2026").insert({
                        "fecha": str(fecha_mov),
                        "concepto": concepto_mov,
                        "monto": monto_mov,
                        "tipo": tipo_db
                    }).execute()
                    cargar_datos.clear()
                    st.success("✅ Movimiento registrado")
                    st.rerun()
                except Exception as e:
                    logger.error(f"Error al registrar movimiento: {e}")
                    st.error(f"❌ Error: {str(e)}")
    
    if not df_gastos_filtrados.empty:
        st.dataframe(
            df_gastos_filtrados.style.format({"Monto": "${:,.2f}"}),
            use_container_width=True,
            hide_index=True
        )
        
        with st.expander("Borrar Movimiento"):
            id_borrar = st.number_input("ID a borrar", step=1, min_value=1)
            if st.button("Eliminar Movimiento"):
                try:
                    supabase.table("gastos_fijos_2026").delete().eq("id", id_borrar).execute()
                    cargar_datos.clear()
                    st.success("✅ Movimiento eliminado")
                    st.rerun()
                except Exception as e:
                    logger.error(f"Error al eliminar movimiento: {e}")
                    st.error(f"❌ Error: {str(e)}")

# ==================== TAB: NUEVA OPERACIÓN ====================

with tab_nueva_op:
    with st.form("add_viaje", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns(4)
        
        fecha_operacion = col1.date_input("Fecha", date.today())
        producto = col2.selectbox("Fruta", obtener_opciones(df_ventas, 'Producto', ["Plátano", "Guayabo"]))
        nuevo_producto = col2.text_input("¿Otra fruta?", placeholder="Opcional")
        proveedor = col3.selectbox("Proveedor", obtener_opciones(df_ventas, 'Proveedor', ["Omar", "Rancho"]))
        nuevo_proveedor = col3.text_input("¿Otro proveedor?", placeholder="Opcional")
        cliente = col4.selectbox("Cliente", obtener_opciones(df_ventas, 'Cliente', ["Calima", "Fogón"]))
        nuevo_cliente = col4.text_input("¿Otro cliente?", placeholder="Opcional")
        
        col_compra, col_venta = st.columns(2)
        
        with col_compra:
            st.markdown("##### 🛒 Compra")
            kg_compra = st.number_input("Kg Compra", min_value=0.0, format="%.2f")
            precio_compra = st.number_input("Precio Compra ($/kg)", min_value=0.0, format="%.2f")
            precio_plaza = st.number_input("Precio Plaza ($/kg)", min_value=0.0, format="%.2f")
            
            st.markdown("**Costos Adicionales**")
            cc1, cc2, cc3 = st.columns(3)
            viaticos = cc1.number_input("Viáticos", min_value=0.0, format="%.2f")
            fletes = cc2.number_input("Fletes", min_value=0.0, format="%.2f")
            otros_gastos = cc3.number_input("Otros Gastos", min_value=0.0, format="%.2f")
            
            file_compra = st.file_uploader("Factura Compra", type=list(ALLOWED_FILE_EXTENSIONS))
        
        with col_venta:
            st.markdown("##### 🤝 Venta")
            kg_venta = st.number_input("Kg Venta", min_value=0.0, format="%.2f")
            precio_venta = st.number_input("Precio Venta ($/kg)", min_value=0.0, format="%.2f")
            
            st.markdown("**Deducciones**")
            cv1, cv2 = st.columns(2)
            retenciones = cv1.number_input("Retenciones", min_value=0.0, format="%.2f")
            descuentos = cv2.number_input("Descuentos", min_value=0.0, format="%.2f")
            
            file_venta = st.file_uploader("Factura Venta", type=list(ALLOWED_FILE_EXTENSIONS))
        
        utilidad_bruta_calc = calcular_utilidad_bruta(
            kg_venta, precio_venta, kg_compra, precio_compra, viaticos, fletes, otros_gastos
        )
        utilidad_neta_calc = calcular_utilidad_neta(
            kg_venta, precio_venta, kg_compra, precio_compra,
            viaticos, fletes, otros_gastos, retenciones, descuentos
        )
        
        col_calc1, col_calc2 = st.columns(2)
        with col_calc1:
            costo_neto = (kg_compra * precio_compra) + viaticos + fletes + otros_gastos
            st.info(f"💵 Costo Neto: ${costo_neto:,.0f}")
            if utilidad_bruta_calc >= 0:
                st.success(f"📊 Utilidad Bruta: ${utilidad_bruta_calc:,.0f}")
            else:
                st.error(f"📊 Pérdida Bruta: ${abs(utilidad_bruta_calc):,.0f}")
        
        with col_calc2:
            if utilidad_neta_calc >= 0:
                st.success(f"💰 Utilidad Neta: ${utilidad_neta_calc:,.0f}")
            else:
                st.error(f"⚠️ Pérdida Neta: ${abs(utilidad_neta_calc):,.0f}")
        
        estado_pago = st.selectbox("Estado", ["Pagado", "Pendiente"])
        dias_credito = st.number_input("Días Crédito", value=DEFAULT_CREDITO_DIAS, min_value=0)
        
        if st.form_submit_button("💾 Guardar Operación"):
            producto_final = nuevo_producto or producto
            proveedor_final = nuevo_proveedor or proveedor
            cliente_final = nuevo_cliente or cliente
            
            es_valida, advertencias, errores = validar_operacion_comercial(
                kg_compra, precio_compra, kg_venta, precio_venta,
                viaticos, fletes, otros_gastos, retenciones, descuentos
            )
            
            if errores:
                for error in errores:
                    st.error(f"❌ {error}")
            
            if advertencias:
                for advertencia in advertencias:
                    st.warning(advertencia)
            
            if es_valida and proveedor_final and cliente_final:
                with st.spinner("Guardando operación..."):
                    try:
                        url_compra = subir_archivo(file_compra, f"c_{proveedor_final}")
                        url_venta = subir_archivo(file_venta, f"v_{cliente_final}")
                        
                        datos_operacion = {
                            "fecha": str(fecha_operacion),
                            "producto": producto_final,
                            "proveedor": proveedor_final,
                            "cliente": cliente_final,
                            "kg_compra": kg_compra,
                            "precio_compra": precio_compra,
                            "viaticos": viaticos,
                            "fletes": fletes,
                            "otros_gastos": otros_gastos,
                            "kg_venta": kg_venta,
                            "precio_venta": precio_venta,
                            "retenciones": retenciones,
                            "descuentos": descuentos,
                            "utilidad": utilidad_neta_calc,
                            "estado_pago": estado_pago,
                            "dias_credito": dias_credito,
                            "precio_plaza": precio_plaza,
                            "fec_doc_url": url_compra if url_compra else "",
                            "fev_doc_url": url_venta if url_venta else ""
                        }
                        
                        supabase.table("ventas_2026").insert(datos_operacion).execute()
                        cargar_datos.clear()
                        st.success("✅ ¡Operación registrada exitosamente!")
                        st.rerun()
                        
                    except Exception as e:
                        logger.error(f"Error al guardar operación: {e}")
                        st.error(f"❌ Error al guardar: {str(e)}")
            elif not proveedor_final or not cliente_final:
                st.error("❌ Proveedor y Cliente son obligatorios")

# ==================== TAB: CARTERA ====================

with tab_cartera:
    if not df_ventas_filtradas.empty:
        config_columnas = {
            "FEC_Doc": st.column_config.LinkColumn("F.C", display_text="Ver"),
            "FEV_Doc": st.column_config.LinkColumn("F.V", display_text="Ver"),
            "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "Utilidad": st.column_config.NumberColumn("Utilidad Neta", format="$%d"),
        }
        
        evento = st.dataframe(
            df_ventas_filtradas.style.apply(color_deuda, axis=1),
            use_container_width=True,
            column_config=config_columnas,
            selection_mode="single-row",
            on_select="rerun",
            hide_index=True
        )
        
        if evento.selection.rows:
            fila = df_ventas_filtradas.iloc[evento.selection.rows[0]]
            st.divider()
            st.markdown(f"### ✏️ Editando: **{fila['Fecha'].strftime('%d-%b')}** - {fila['Cliente']}")
            
            with st.form("edit_full"):
                col1, col2, col3, col4 = st.columns(4)
                
                e_fecha = col1.date_input("Fecha", value=pd.to_datetime(fila['Fecha']).date())
                e_cliente = col2.text_input("Cliente", value=fila['Cliente'])
                e_prov = col3.text_input("Proveedor", value=fila['Proveedor'])
                e_prod = col4.text_input("Producto", value=fila['Producto'])
                
                st.markdown("**Datos Compra**")
                cc1, cc2, cc3 = st.columns(3)
                e_kgc = cc1.number_input("Kg Compra", value=float(fila['Kg_Compra']), format="%.2f")
                e_pc = cc2.number_input("Precio Compra", value=float(fila['Precio_Compra']), format="%.2f")
                e_plaza = cc3.number_input("Precio Plaza", value=float(fila['Precio_Plaza']), format="%.2f")
                
                st.markdown("**Costos Adicionales**")
                cc4, cc5, cc6 = st.columns(3)
                e_viat = cc4.number_input("Viáticos", value=float(fila.get('Viaticos', 0.0)), format="%.2f")
                e_flete = cc5.number_input("Fletes", value=float(fila.get('Fletes', 0.0)), format="%.2f")
                e_otros = cc6.number_input("Otros Gastos", value=float(fila.get('Otros_Gastos', 0.0)), format="%.2f")
                
                st.markdown("**Datos Venta**")
                cv1, cv2, cv3, cv4 = st.columns(4)
                e_kgv = cv1.number_input("Kg Venta", value=float(fila['Kg_Venta']), format="%.2f")
                e_pv = cv2.number_input("Precio Venta", value=float(fila['Precio_Venta']), format="%.2f")
                e_ret = cv3.number_input("Retenciones", value=float(fila.get('Retenciones', 0.0)), format="%.2f")
                e_desc = cv4.number_input("Descuentos", value=float(fila.get('Descuentos', 0.0)), format="%.2f")
                
                e_est = st.selectbox("Estado Pago", ["Pagado", "Pendiente"],
                                    index=0 if fila['Estado_Pago'] == "Pagado" else 1)
                
                st.markdown("**Soportes (Subir para reemplazar)**")
                cf1, cf2 = st.columns(2)
                new_file_c = cf1.file_uploader("Nueva F.Compra", type=list(ALLOWED_FILE_EXTENSIONS))
                new_file_v = cf2.file_uploader("Nueva F.Venta", type=list(ALLOWED_FILE_EXTENSIONS))
                
                if st.form_submit_button("💾 Guardar Cambios"):
                    es_valida, advertencias, errores = validar_operacion_comercial(
                        e_kgc, e_pc, e_kgv, e_pv, e_viat, e_flete, e_otros, e_ret, e_desc
                    )
                    
                    if errores:
                        for error in errores:
                            st.error(f"❌ {error}")
                    
                    if advertencias:
                        for advertencia in advertencias:
                            st.warning(advertencia)
                    
                    if es_valida:
                        try:
                            nueva_utilidad = calcular_utilidad_neta(
                                e_kgv, e_pv, e_kgc, e_pc, e_viat, e_flete, e_otros, e_ret, e_desc
                            )
                            
                            actualizaciones = {
                                "fecha": str(e_fecha),
                                "cliente": e_cliente,
                                "proveedor": e_prov,
                                "producto": e_prod,
                                "kg_compra": e_kgc,
                                "precio_compra": e_pc,
                                "precio_plaza": e_plaza,
                                "viaticos": e_viat,
                                "fletes": e_flete,
                                "otros_gastos": e_otros,
                                "kg_venta": e_kgv,
                                "precio_venta": e_pv,
                                "retenciones": e_ret,
                                "descuentos": e_desc,
                                "estado_pago": e_est,
                                "utilidad": nueva_utilidad
                            }
                            
                            if new_file_c:
                                u = subir_archivo(new_file_c, f"e_c_{e_prov}")
                                if u:
                                    actualizaciones["fec_doc_url"] = u
                            
                            if new_file_v:
                                u = subir_archivo(new_file_v, f"e_v_{e_cliente}")
                                if u:
                                    actualizaciones["fev_doc_url"] = u
                            
                            supabase.table("ventas_2026").update(actualizaciones).eq(
                                "id", int(fila['ID'])
                            ).execute()
                            
                            cargar_datos.clear()
                            st.success("✅ Registro actualizado exitosamente")
                            st.rerun()
                            
                        except Exception as e:
                            logger.error(f"Error al actualizar registro: {e}")
                            st.error(f"❌ Error al actualizar: {str(e)}")
            
            if st.button("🗑️ Borrar Registro"):
                try:
                    supabase.table("ventas_2026").delete().eq("id", int(fila['ID'])).execute()
                    cargar_datos.clear()
                    st.success("✅ Registro eliminado")
                    st.rerun()
                except Exception as e:
                    logger.error(f"Error al borrar registro: {e}")
                    st.error(f"❌ Error al borrar: {str(e)}")
