"""
Sistema de Gestión Agrícola Montserrat - Versión Refactorizada
Mejoras implementadas:
- Validación completa de datos de entrada
- Manejo robusto de excepciones con logging
- Código modularizado y documentado
- Optimización de caché
- Validación de archivos
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta, datetime
from supabase import create_client
import io
import re
import unicodedata
import logging

# ==================== CONFIGURACIÓN ====================

# Configurar logging
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constantes de configuración
CACHE_TTL_SECONDS = 300  # 5 minutos (reducido de 5s para menor carga en DB)
DEFAULT_CREDITO_DIAS = 8
ALLOWED_FILE_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
PAGE_SIZE = 50  # Para paginación de tablas

# Configuración de página
st.set_page_config(
    page_title="Agrícola Montserrat", 
    layout="wide", 
    page_icon="🍌"
)

# Estilos CSS
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
    """
    Valida que una cantidad sea un número positivo válido.
    
    Args:
        valor: Valor numérico a validar
        nombre_campo: Nombre del campo para mensajes de error
        permitir_cero: Si se permite valor 0
        
    Returns:
        tuple: (es_valido: bool, mensaje_error: str)
    """
    if valor is None:
        return False, f"{nombre_campo} no puede estar vacío"
    
    if not permitir_cero and valor <= 0:
        return False, f"{nombre_campo} debe ser mayor a 0"
    
    if permitir_cero and valor < 0:
        return False, f"{nombre_campo} no puede ser negativo"
    
    if valor > 1000000:  # Límite razonable
        return False, f"{nombre_campo} excede el límite permitido"
    
    return True, ""

def validar_operacion_comercial(kg_compra, precio_compra, kg_venta, precio_venta, fletes, descuentos):
    """
    Valida la coherencia de una operación comercial completa.
    
    Returns:
        tuple: (es_valida: bool, lista_advertencias: list, lista_errores: list)
    """
    errores = []
    advertencias = []
    
    # Validar cantidades individuales
    validaciones = [
        (kg_compra, "Kg Compra"),
        (precio_compra, "Precio Compra"),
        (kg_venta, "Kg Venta"),
        (precio_venta, "Precio Venta"),
        (fletes, "Fletes", True),
        (descuentos, "Descuentos", True)
    ]
    
    for validacion in validaciones:
        permitir_cero = validacion[2] if len(validacion) > 2 else False
        es_valido, mensaje = validar_cantidad(validacion[0], validacion[1], permitir_cero)
        if not es_valido:
            errores.append(mensaje)
    
    if errores:
        return False, advertencias, errores
    
    # Validaciones de lógica de negocio
    if kg_venta > kg_compra * 1.1:  # 10% de tolerancia por diferencias de peso
        advertencias.append(
            f"⚠️ Vendes {kg_venta - kg_compra:.2f} kg más de lo que compraste. "
            "Verifica si hay stock previo."
        )
    
    if precio_venta < precio_compra * 0.9:  # Margen negativo significativo
        margen = ((precio_venta - precio_compra) / precio_compra) * 100
        advertencias.append(
            f"⚠️ Pérdida en precio: vendes a ${precio_venta:,.0f} "
            f"vs compra de ${precio_compra:,.0f} ({margen:.1f}%)"
        )
    
    # Calcular utilidad
    utilidad = calcular_utilidad(kg_venta, precio_venta, kg_compra, precio_compra, fletes, descuentos)
    
    if utilidad < 0:
        advertencias.append(f"💰 Utilidad negativa: ${utilidad:,.0f}")
    
    return True, advertencias, errores

def validar_archivo(archivo):
    """
    Valida tipo y tamaño de archivo antes de subirlo.
    
    Args:
        archivo: Objeto de archivo de Streamlit
        
    Returns:
        tuple: (es_valido: bool, mensaje_error: str)
    """
    if not archivo:
        return True, ""  # Archivo opcional
    
    # Validar extensión
    ext = archivo.name.split('.')[-1].lower()
    if ext not in ALLOWED_FILE_EXTENSIONS:
        return False, f"Formato no permitido. Usa: {', '.join(ALLOWED_FILE_EXTENSIONS)}"
    
    # Validar tamaño
    archivo.seek(0, 2)  # Ir al final del archivo
    size = archivo.tell()
    archivo.seek(0)  # Volver al inicio
    
    if size > MAX_FILE_SIZE_BYTES:
        return False, f"Archivo muy grande ({size/1024/1024:.1f}MB). Máximo: {MAX_FILE_SIZE_MB}MB"
    
    return True, ""

# ==================== FUNCIONES DE NEGOCIO ====================

def calcular_utilidad(kg_venta, precio_venta, kg_compra, precio_compra, fletes, descuentos):
    """
    Calcula la utilidad neta de una operación comercial.
    
    Args:
        kg_venta: Kilogramos vendidos
        precio_venta: Precio por kg de venta
        kg_compra: Kilogramos comprados
        precio_compra: Precio por kg de compra
        fletes: Costos de transporte
        descuentos: Deducciones aplicadas
        
    Returns:
        float: Utilidad neta (puede ser negativa si hay pérdida)
    """
    ingreso_bruto = kg_venta * precio_venta
    costo_total = (kg_compra * precio_compra) + fletes + descuentos
    return ingreso_bruto - costo_total

def limpiar_nombre_archivo(nombre):
    """
    Limpia nombre de archivo removiendo caracteres especiales.
    
    Args:
        nombre: Nombre original del archivo
        
    Returns:
        str: Nombre limpio con solo letras, números y guiones bajos
    """
    # Remover acentos
    nombre = unicodedata.normalize('NFKD', nombre).encode('ASCII', 'ignore').decode('utf-8')
    # Reemplazar caracteres especiales con guion bajo
    nombre = re.sub(r'[^\w]', '_', nombre)
    return nombre

def color_deuda(row):
    """
    Aplica colores condicionales a filas de dataframe según estado de pago.
    
    Args:
        row: Fila de pandas DataFrame con columnas 'Estado_Pago', 'Fecha', 'Dias_Credito'
        
    Returns:
        list: Lista de estilos CSS para cada celda
        
    Colores aplicados:
        - Verde: Pagado
        - Amarillo: Vence en ≤3 días
        - Rojo: Vencido
    """
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
    """
    Obtiene lista única de opciones combinando valores existentes con defaults.
    
    Args:
        df: DataFrame de pandas
        columna: Nombre de la columna
        valores_default: Lista de valores predeterminados
        
    Returns:
        list: Lista ordenada de opciones únicas
    """
    existentes = df[columna].unique().tolist() if not df.empty and columna in df.columns else []
    todas = list(set(valores_default + [x for x in existentes if x]))
    return sorted(todas)

# ==================== FUNCIONES DE BASE DE DATOS ====================

def subir_archivo(archivo, nombre_base):
    """
    Sube un archivo a Supabase Storage con validación.
    
    Args:
        archivo: Objeto de archivo de Streamlit
        nombre_base: Nombre base para el archivo (se limpiará)
        
    Returns:
        str: URL pública del archivo o None si falla
    """
    if not archivo:
        return None
    
    # Validar archivo
    es_valido, mensaje_error = validar_archivo(archivo)
    if not es_valido:
        st.error(f"❌ {mensaje_error}")
        return None
    
    try:
        # Preparar nombre de archivo
        ext = archivo.name.split('.')[-1].lower()
        nombre_limpio = limpiar_nombre_archivo(nombre_base)
        timestamp = datetime.now().strftime('%m%d_%H%M')
        nombre_archivo = f"{nombre_limpio}_{timestamp}.{ext}"
        
        # Subir archivo
        supabase.storage.from_(BUCKET_FACTURAS).upload(
            nombre_archivo,
            archivo.getvalue(),
            {
                "content-type": archivo.type,
                "upsert": "true"
            }
        )
        
        # Obtener URL pública
        url_publica = supabase.storage.from_(BUCKET_FACTURAS).get_public_url(nombre_archivo)
        logger.info(f"Archivo subido exitosamente: {nombre_archivo}")
        return url_publica
        
    except Exception as e:
        logger.error(f"Error al subir archivo: {e}")
        st.error(f"❌ Error al subir archivo: {str(e)}")
        return None

@st.cache_data(ttl=CACHE_TTL_SECONDS)
def cargar_datos():
    """
    Carga datos de ventas, gastos y configuración desde Supabase.
    
    Returns:
        tuple: (df_ventas, df_gastos, saldo_inicial)
    """
    # Cargar ventas
    df_ventas = pd.DataFrame()
    try:
        respuesta = supabase.table("ventas_2026").select("*").order("fecha", desc=True).execute()
        df_ventas = pd.DataFrame(respuesta.data)
        
        if not df_ventas.empty:
            # Renombrar columnas
            columnas_mapa = {
                'id': 'ID', 'fecha': 'Fecha', 'producto': 'Producto', 
                'proveedor': 'Proveedor', 'cliente': 'Cliente',
                'fec_doc_url': 'FEC_Doc', 'fev_doc_url': 'FEV_Doc',
                'kg_compra': 'Kg_Compra', 'precio_compra': 'Precio_Compra',
                'fletes': 'Fletes', 'kg_venta': 'Kg_Venta',
                'precio_venta': 'Precio_Venta', 'descuentos': 'Descuentos',
                'utilidad': 'Utilidad', 'estado_pago': 'Estado_Pago',
                'dias_credito': 'Dias_Credito', 'precio_plaza': 'Precio_Plaza'
            }
            df_ventas = df_ventas.rename(
                columns={k: v for k, v in columnas_mapa.items() if k in df_ventas.columns}
            )
            
            # Convertir tipos
            df_ventas['Fecha'] = pd.to_datetime(df_ventas['Fecha'])
            
            # Limpiar campos numéricos
            campos_numericos = [
                'Kg_Compra', 'Precio_Compra', 'Fletes', 'Kg_Venta',
                'Precio_Venta', 'Descuentos', 'Utilidad', 'Precio_Plaza'
            ]
            for campo in campos_numericos:
                if campo in df_ventas.columns:
                    df_ventas[campo] = pd.to_numeric(df_ventas[campo], errors='coerce').fillna(0.0)
            
            # Limpiar URLs
            for campo in ['FEC_Doc', 'FEV_Doc']:
                if campo in df_ventas.columns:
                    df_ventas[campo] = df_ventas[campo].replace(
                        {'': None, 'None': None, 'nan': None}
                    )
                    
    except Exception as e:
        logger.error(f"Error al cargar ventas: {e}")
        st.error(f"⚠️ Error al cargar ventas: {str(e)}")
    
    # Cargar gastos
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
    
    # Cargar saldo inicial
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
    """Verifica la contraseña de acceso."""
    if st.session_state.get("password_input") == st.secrets.get("APP_PASSWORD"):
        st.session_state["password_correct"] = True
        del st.session_state["password_input"]
    else:
        st.error("😕 Clave incorrecta.")

if not st.session_state.get("password_correct", False):
    st.title("🔐 Acceso Restringido")
    st.text_input(
        "Ingresa la clave maestra:",
        type="password",
        key="password_input",
        on_change=verificar_password
    )
    st.stop()

# ==================== CONEXIÓN A SUPABASE ====================

try:
    supabase = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"]
    )
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

# Barra lateral
st.sidebar.title("Menú")
if st.sidebar.button("🔄 Actualizar Datos"):
    cargar_datos.clear()
    st.rerun()

st.sidebar.divider()

# Filtros de fecha
fecha_inicio = st.sidebar.date_input("📅 Inicio", date(2026, 1, 1))
fecha_fin = st.sidebar.date_input("📅 Fin", date(2026, 12, 31))

# Cargar datos
df_ventas, df_gastos, saldo_inicial = cargar_datos()

# ==================== CÁLCULOS FINANCIEROS ====================

ingresos_caja = 0.0
egresos_caja = 0.0

# Calcular ingresos de ventas pagadas
if not df_ventas.empty:
    ventas_pagadas = df_ventas[df_ventas['Estado_Pago'] == 'Pagado']
    ingresos_caja += (ventas_pagadas['Kg_Venta'] * ventas_pagadas['Precio_Venta']).sum()
    
    # Calcular egresos de compras y fletes
    compras_total = (df_ventas['Kg_Compra'] * df_ventas['Precio_Compra']).sum()
    fletes_total = df_ventas['Fletes'].sum()
    egresos_caja += compras_total + fletes_total

# Procesar gastos y otros movimientos
if not df_gastos.empty:
    gastos_operativos = df_gastos[df_gastos['Tipo'] == 'Gasto']
    egresos_caja += gastos_operativos['Monto'].sum()
    
    prestamos_salida = df_gastos[df_gastos['Tipo'] == 'Préstamo Salida']
    egresos_caja += prestamos_salida['Monto'].sum()
    
    ingresos_extra = df_gastos[df_gastos['Tipo'] == 'Ingreso Extra']
    ingresos_caja += ingresos_extra['Monto'].sum()

# Calcular flujo y caja final
flujo_acumulado = ingresos_caja - egresos_caja
caja_sistema = saldo_inicial + flujo_acumulado

# ==================== CALIBRACIÓN DE CAJA ====================

st.sidebar.divider()
st.sidebar.subheader("💰 Calibrar Caja")

with st.sidebar.form("config_caja"):
    st.caption(f"Sistema: ${caja_sistema:,.0f}")
    valor_real = st.number_input(
        "Realidad HOY:",
        value=float(caja_sistema),
        format="%.2f"
    )
    
    if st.form_submit_button("✅ Ajustar"):
        try:
            nueva_base = valor_real - flujo_acumulado
            supabase.table("configuracion_caja").update(
                {"saldo_inicial": nueva_base}
            ).gt("id", 0).execute()
            cargar_datos.clear()
            st.success("✅ Caja ajustada exitosamente")
            st.rerun()
        except Exception as e:
            logger.error(f"Error al ajustar caja: {e}")
            st.error(f"❌ Error al ajustar: {str(e)}")

# ==================== FILTROS DE DATOS ====================

# Filtrar ventas por rango de fechas
df_ventas_filtradas = df_ventas[
    (df_ventas['Fecha'].dt.date >= fecha_inicio) &
    (df_ventas['Fecha'].dt.date <= fecha_fin)
].copy() if not df_ventas.empty else pd.DataFrame()

# Filtrar gastos por rango de fechas
df_gastos_filtrados = df_gastos[
    (df_gastos['Fecha'].dt.date >= fecha_inicio) &
    (df_gastos['Fecha'].dt.date <= fecha_fin)
].copy() if not df_gastos.empty else pd.DataFrame(columns=['ID', 'Fecha', 'Concepto', 'Monto', 'Tipo'])

# ==================== ALERTAS ====================

if not df_ventas.empty:
    pendientes = df_ventas[df_ventas['Estado_Pago'] == 'Pendiente'].copy()
    
    if not pendientes.empty:
        pendientes['Dias_Credito'] = pd.to_numeric(
            pendientes['Dias_Credito'],
            errors='coerce'
        ).fillna(0)
        pendientes['Vence'] = pendientes['Fecha'] + pd.to_timedelta(
            pendientes['Dias_Credito'],
            unit='D'
        )
        
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
    
    utilidad_bruta = df_ventas_filtradas['Utilidad'].sum() if not df_ventas_filtradas.empty else 0
    gastos_periodo = df_gastos_filtrados[df_gastos_filtrados['Tipo'] == 'Gasto']['Monto'].sum() \
        if not df_gastos_filtrados.empty else 0
    utilidad_neta = utilidad_bruta - gastos_periodo
    volumen_total = df_ventas_filtradas['Kg_Venta'].sum() if not df_ventas_filtradas.empty else 0
    
    col1, col2, col3 = st.columns(3)
    col1.metric("💰 CAJA REAL", f"${caja_sistema:,.0f}", delta="Disponible")
    col2.metric("Utilidad Neta", f"${utilidad_neta:,.0f}", delta="Real")
    col3.metric("Volumen", f"{volumen_total:,.1f} Kg")

# ==================== TAB: ANALÍTICA ====================

with tab_analitica:
    if not df_ventas_filtradas.empty:
        df_precios = df_ventas_filtradas[df_ventas_filtradas['Precio_Plaza'] > 0].sort_values("Fecha")
        
        col_grafico, col_metrica = st.columns([3, 1])
        
        with col_grafico:
            if not df_precios.empty:
                fig = px.line(
                    df_precios,
                    x='Fecha',
                    y=['Precio_Compra', 'Precio_Plaza'],
                    markers=True,
                    title="Precios: Compra vs Plaza"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Faltan datos de precio de plaza.")
        
        with col_metrica:
            if not df_precios.empty:
                precio_plaza_promedio = df_precios['Precio_Plaza'].mean()
                precio_compra_promedio = df_precios['Precio_Compra'].mean()
                ahorro_promedio = precio_plaza_promedio - precio_compra_promedio
                
                st.metric(
                    "Margen vs Plaza",
                    f"${ahorro_promedio:,.0f}",
                    delta="Ahorro/Kg" if ahorro_promedio > 0 else "Sobrecosto"
                )

# ==================== TAB: MOVIMIENTOS ====================

with tab_movimientos:
    st.subheader("💸 Registro de Movimientos")
    
    with st.form("add_movimiento", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns(4)
        
        fecha_mov = col1.date_input("Fecha", date.today())
        concepto_mov = col2.text_input("Concepto")
        tipo_mov = col3.selectbox("Tipo", [
            "Gasto (Gasolina/Nómina)",
            "Préstamo Salida",
            "Ingreso Extra"
        ])
        monto_mov = col4.number_input("Valor ($)", min_value=0.0, format="%.2f")
        
        if st.form_submit_button("Registrar"):
            # Mapear tipo para base de datos
            tipo_db = "Gasto"
            if "Préstamo" in tipo_mov:
                tipo_db = "Préstamo Salida"
            elif "Ingreso" in tipo_mov:
                tipo_db = "Ingreso Extra"
            
            # Validar datos
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
    
    # Mostrar tabla de movimientos
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
        
        producto = col2.selectbox(
            "Fruta",
            obtener_opciones(df_ventas, 'Producto', ["Plátano", "Guayabo"])
        )
        nuevo_producto = col2.text_input("¿Otra fruta?", placeholder="Opcional")
        
        proveedor = col3.selectbox(
            "Proveedor",
            obtener_opciones(df_ventas, 'Proveedor', ["Omar", "Rancho"])
        )
        nuevo_proveedor = col3.text_input("¿Otro proveedor?", placeholder="Opcional")
        
        cliente = col4.selectbox(
            "Cliente",
            obtener_opciones(df_ventas, 'Cliente', ["Calima", "Fogón"])
        )
        nuevo_cliente = col4.text_input("¿Otro cliente?", placeholder="Opcional")
        
        col_compra, col_venta = st.columns(2)
        
        with col_compra:
            st.markdown("##### 🛒 Compra")
            kg_compra = st.number_input("Kg Compra", min_value=0.0, format="%.2f")
            precio_compra = st.number_input("Precio Compra", min_value=0.0, format="%.2f")
            precio_plaza = st.number_input("Precio Plaza", min_value=0.0, format="%.2f")
            fletes = st.number_input("Fletes", min_value=0.0, format="%.2f")
            file_compra = st.file_uploader("Factura Compra", type=list(ALLOWED_FILE_EXTENSIONS))
        
        with col_venta:
            st.markdown("##### 🤝 Venta")
            kg_venta = st.number_input("Kg Venta", min_value=0.0, format="%.2f")
            precio_venta = st.number_input("Precio Venta", min_value=0.0, format="%.2f")
            descuentos = st.number_input("Deducciones", min_value=0.0, format="%.2f")
            file_venta = st.file_uploader("Factura Venta", type=list(ALLOWED_FILE_EXTENSIONS))
        
        # Calcular utilidad estimada
        utilidad_estimada = calcular_utilidad(
            kg_venta, precio_venta, kg_compra, precio_compra, fletes, descuentos
        )
        
        # Mostrar utilidad con color
        if utilidad_estimada >= 0:
            st.success(f"💰 Utilidad Estimada: ${utilidad_estimada:,.2f}")
        else:
            st.error(f"⚠️ Pérdida Estimada: ${abs(utilidad_estimada):,.2f}")
        
        estado_pago = st.selectbox("Estado", ["Pagado", "Pendiente"])
        dias_credito = st.number_input("Días Crédito", value=DEFAULT_CREDITO_DIAS, min_value=0)
        
        if st.form_submit_button("Guardar Viaje"):
            # Determinar valores finales
            producto_final = nuevo_producto or producto
            proveedor_final = nuevo_proveedor or proveedor
            cliente_final = nuevo_cliente or cliente
            
            # Validar operación
            es_valida, advertencias, errores = validar_operacion_comercial(
                kg_compra, precio_compra, kg_venta, precio_venta, fletes, descuentos
            )
            
            # Mostrar errores
            if errores:
                for error in errores:
                    st.error(f"❌ {error}")
            
            # Mostrar advertencias
            if advertencias:
                for advertencia in advertencias:
                    st.warning(advertencia)
            
            # Proceder si es válida
            if es_valida and proveedor_final and cliente_final:
                with st.spinner("Guardando operación..."):
                    try:
                        # Subir archivos
                        url_compra = subir_archivo(file_compra, f"c_{proveedor_final}")
                        url_venta = subir_archivo(file_venta, f"v_{cliente_final}")
                        
                        # Preparar datos
                        datos_operacion = {
                            "fecha": str(fecha_operacion),
                            "producto": producto_final,
                            "proveedor": proveedor_final,
                            "cliente": cliente_final,
                            "kg_compra": kg_compra,
                            "precio_compra": precio_compra,
                            "fletes": fletes,
                            "kg_venta": kg_venta,
                            "precio_venta": precio_venta,
                            "descuentos": descuentos,
                            "utilidad": utilidad_estimada,
                            "estado_pago": estado_pago,
                            "dias_credito": dias_credito,
                            "precio_plaza": precio_plaza,
                            "fec_doc_url": url_compra if url_compra else "",
                            "fev_doc_url": url_venta if url_venta else ""
                        }
                        
                        # Insertar en base de datos
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
        # Configuración de columnas
        config_columnas = {
            "FEC_Doc": st.column_config.LinkColumn("F.C", display_text="Ver"),
            "FEV_Doc": st.column_config.LinkColumn("F.V", display_text="Ver"),
            "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "Utilidad": st.column_config.NumberColumn("Utilidad", format="$%d"),
        }
        
        # Mostrar tabla interactiva
        evento = st.dataframe(
            df_ventas_filtradas.style.apply(color_deuda, axis=1),
            use_container_width=True,
            column_config=config_columnas,
            selection_mode="single-row",
            on_select="rerun",
            hide_index=True
        )
        
        # Edición de registro seleccionado
        if evento.selection.rows:
            fila_seleccionada = df_ventas_filtradas.iloc[evento.selection.rows[0]]
            st.divider()
            st.markdown(f"### ✏️ Editando: **{fila_seleccionada['Fecha'].strftime('%d-%b')}**")
            
            with st.form("edit_full"):
                col1, col2, col3, col4 = st.columns(4)
                
                edit_fecha = col1.date_input(
                    "Fecha Original",
                    value=pd.to_datetime(fila_seleccionada['Fecha']).date()
                )
                edit_cliente = col2.text_input("Cliente", value=fila_seleccionada['Cliente'])
                edit_proveedor = col3.text_input("Proveedor", value=fila_seleccionada['Proveedor'])
                edit_producto = col4.text_input("Producto", value=fila_seleccionada['Producto'])
                
                st.markdown("**Datos Compra**")
                cc1, cc2, cc3, cc4 = st.columns(4)
                edit_kg_compra = cc1.number_input(
                    "Kg Compra",
                    value=float(fila_seleccionada['Kg_Compra']),
                    format="%.2f"
                )
                edit_precio_compra = cc2.number_input(
                    "Precio Compra",
                    value=float(fila_seleccionada['Precio_Compra']),
                    format="%.2f"
                )
                edit_precio_plaza = cc3.number_input(
                    "Precio Plaza",
                    value=float(fila_seleccionada['Precio_Plaza']),
                    format="%.2f"
                )
                edit_fletes = cc4.number_input(
                    "Fletes",
                    value=float(fila_seleccionada.get('Fletes', 0.0)),
                    format="%.2f"
                )
                
                st.markdown("**Datos Venta**")
                cv1, cv2, cv3, cv4 = st.columns(4)
                edit_kg_venta = cv1.number_input(
                    "Kg Venta",
                    value=float(fila_seleccionada['Kg_Venta']),
                    format="%.2f"
                )
                edit_precio_venta = cv2.number_input(
                    "Precio Venta",
                    value=float(fila_seleccionada['Precio_Venta']),
                    format="%.2f"
                )
                edit_descuentos = cv3.number_input(
                    "Deducciones",
                    value=float(fila_seleccionada.get('Descuentos', 0.0)),
                    format="%.2f"
                )
                edit_estado = cv4.selectbox(
                    "Estado Pago",
                    ["Pagado", "Pendiente"],
                    index=0 if fila_seleccionada['Estado_Pago'] == "Pagado" else 1
                )
                
                st.markdown("**Soportes (Subir para reemplazar)**")
                cf1, cf2 = st.columns(2)
                nuevo_file_compra = cf1.file_uploader(
                    "Nueva F.Compra",
                    type=list(ALLOWED_FILE_EXTENSIONS)
                )
                nuevo_file_venta = cf2.file_uploader(
                    "Nueva F.Venta",
                    type=list(ALLOWED_FILE_EXTENSIONS)
                )
                
                if st.form_submit_button("💾 Guardar Cambios"):
                    # Validar
                    es_valida, advertencias, errores = validar_operacion_comercial(
                        edit_kg_compra, edit_precio_compra, edit_kg_venta,
                        edit_precio_venta, edit_fletes, edit_descuentos
                    )
                    
                    if errores:
                        for error in errores:
                            st.error(f"❌ {error}")
                    
                    if advertencias:
                        for advertencia in advertencias:
                            st.warning(advertencia)
                    
                    if es_valida:
                        try:
                            # Calcular nueva utilidad
                            nueva_utilidad = calcular_utilidad(
                                edit_kg_venta, edit_precio_venta, edit_kg_compra,
                                edit_precio_compra, edit_fletes, edit_descuentos
                            )
                            
                            # Preparar actualizaciones
                            actualizaciones = {
                                "fecha": str(edit_fecha),
                                "cliente": edit_cliente,
                                "proveedor": edit_proveedor,
                                "producto": edit_producto,
                                "kg_compra": edit_kg_compra,
                                "precio_compra": edit_precio_compra,
                                "precio_plaza": edit_precio_plaza,
                                "fletes": edit_fletes,
                                "kg_venta": edit_kg_venta,
                                "precio_venta": edit_precio_venta,
                                "descuentos": edit_descuentos,
                                "estado_pago": edit_estado,
                                "utilidad": nueva_utilidad
                            }
                            
                            # Subir nuevos archivos si existen
                            if nuevo_file_compra:
                                url = subir_archivo(nuevo_file_compra, f"e_c_{edit_proveedor}")
                                if url:
                                    actualizaciones["fec_doc_url"] = url
                            
                            if nuevo_file_venta:
                                url = subir_archivo(nuevo_file_venta, f"e_v_{edit_cliente}")
                                if url:
                                    actualizaciones["fev_doc_url"] = url
                            
                            # Actualizar en base de datos
                            supabase.table("ventas_2026").update(actualizaciones).eq(
                                "id",
                                int(fila_seleccionada['ID'])
                            ).execute()
                            
                            cargar_datos.clear()
                            st.success("✅ Registro actualizado exitosamente")
                            st.rerun()
                            
                        except Exception as e:
                            logger.error(f"Error al actualizar registro: {e}")
                            st.error(f"❌ Error al actualizar: {str(e)}")
            
            # Botón de borrado
            if st.button("🗑️ Borrar Registro"):
                try:
                    supabase.table("ventas_2026").delete().eq(
                        "id",
                        int(fila_seleccionada['ID'])
                    ).execute()
                    cargar_datos.clear()
                    st.success("✅ Registro eliminado")
                    st.rerun()
                except Exception as e:
                    logger.error(f"Error al borrar registro: {e}")
                    st.error(f"❌ Error al borrar: {str(e)}")
