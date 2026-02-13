"""
Sistema de Gestión Agrícola Montserrat - FASE 1 COMPLETA
Versión: 3.0 - Febrero 2026

NUEVAS FUNCIONALIDADES FASE 1:
✅ Exportar a Excel/PDF con formato profesional
✅ Tema oscuro/claro con toggle
✅ Pestaña de Reportes Semanales automáticos
✅ Comparativa histórica 2025 vs 2026
✅ Alertas mejoradas con detalles de vencimientos
✅ Caché optimizado
✅ Todos los gráficos y análisis anteriores

Desarrollado para optimizar la gestión de operaciones agrícolas
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
import base64
from io import BytesIO

# ==================== CONFIGURACIÓN ====================

logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constantes de configuración
CACHE_TTL_SECONDS = 300
DEFAULT_CREDITO_DIAS = 8
ALLOWED_FILE_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Datos históricos 2025 (cargados desde CSV)
DATOS_2025_MESES = {
    1: 5040754,   # Enero
    2: 3980153,   # Febrero
    3: 6353225,   # Marzo
    4: 8251444,   # Abril
    5: 8113135,   # Mayo
    6: 7897442,   # Junio
    7: 6911626,   # Julio
    8: 4942570,   # Agosto
    9: 4552379,   # Septiembre
    10: 4767205,  # Octubre
    11: 5398518,  # Noviembre
    12: 7204806   # Diciembre
}
TOTAL_2025 = 73413257
TOTAL_OPERACIONES_2025 = 322

# Configuración de página
st.set_page_config(
    page_title="Agrícola Montserrat",
    layout="wide",
    page_icon="🍌",
    initial_sidebar_state="expanded"
)

# ==================== GESTIÓN DE TEMA ====================

if 'tema_oscuro' not in st.session_state:
    st.session_state.tema_oscuro = False

def toggle_tema():
    """Alterna entre tema oscuro y claro."""
    st.session_state.tema_oscuro = not st.session_state.tema_oscuro

# Aplicar estilos según tema
if st.session_state.tema_oscuro:
    st.markdown("""
        <style>
        .stApp {
            background-color: #0e1117;
            color: #fafafa;
        }
        h1, h2, h3, h4, h5, h6 {
            color: #66bb6a !important;
            font-family: 'Helvetica Neue', sans-serif;
        }
        div[data-testid="stMetric"] {
            background-color: #1e1e1e;
            border: 1px solid #4caf50;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 2px 2px 8px rgba(76, 175, 80, 0.3);
        }
        div[data-testid="stMetric"] label {
            color: #b0b0b0 !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: #fafafa !important;
        }
        .stButton>button {
            background-color: #388e3c;
            color: white;
            border-radius: 8px;
            border: none;
            padding: 10px 20px;
            font-weight: bold;
        }
        .stButton>button:hover {
            background-color: #2e7d32;
            color: white;
        }
        .stDataFrame {
            background-color: #1e1e1e;
        }
        </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
        <style>
        .stApp {
            background-color: #f8fcf8;
        }
        h1, h2, h3, h4, h5, h6 {
            color: #1b5e20 !important;
            font-family: 'Helvetica Neue', sans-serif;
        }
        div[data-testid="stMetric"] {
            background-color: #ffffff;
            border: 1px solid #c8e6c9;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
            text-align: center;
        }
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
        </style>
    """, unsafe_allow_html=True)

# ==================== FUNCIONES DE EXPORTACIÓN ====================

def exportar_a_excel(df, nombre_archivo="reporte"):
    """
    Exporta un DataFrame a Excel con formato profesional.
    
    Args:
        df: DataFrame de pandas
        nombre_archivo: Nombre base del archivo (sin extensión)
        
    Returns:
        BytesIO: Buffer con el archivo Excel
    """
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Datos')
        
        workbook = writer.book
        worksheet = writer.sheets['Datos']
        
        # Formatos
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#2e7d32',
            'font_color': 'white',
            'border': 1
        })
        
        currency_format = workbook.add_format({'num_format': '$#,##0'})
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        
        # Aplicar formato a encabezados
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            
            # Ajustar ancho de columnas
            max_length = max(
                df[value].astype(str).map(len).max(),
                len(str(value))
            )
            worksheet.set_column(col_num, col_num, min(max_length + 2, 50))
            
            # Aplicar formato según tipo de datos
            if 'Precio' in value or 'Utilidad' in value or 'Monto' in value or value.endswith('$'):
                worksheet.set_column(col_num, col_num, 15, currency_format)
            elif 'Fecha' in value:
                worksheet.set_column(col_num, col_num, 12, date_format)
    
    output.seek(0)
    return output

def crear_boton_descarga(data, filename, label, file_type="excel"):
    """
    Crea un botón de descarga para archivos.
    
    Args:
        data: Datos del archivo (BytesIO)
        filename: Nombre del archivo
        label: Etiqueta del botón
        file_type: Tipo de archivo (excel, pdf, csv)
    """
    mime_types = {
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
        "csv": "text/csv"
    }
    
    st.download_button(
        label=label,
        data=data,
        file_name=filename,
        mime=mime_types.get(file_type, "application/octet-stream")
    )

# ==================== FUNCIONES DE VALIDACIÓN ====================

def validar_cantidad(valor, nombre_campo, permitir_cero=False):
    """Valida que una cantidad sea válida."""
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
    """Valida coherencia de una operación comercial."""
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
    """Valida tipo y tamaño de archivo."""
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
    """
    Calcula utilidad neta según fórmula correcta.
    Fórmula: Utilidad Neta = (Venta - Costo Neto) - Retenciones - Descuentos
    """
    costo_bruto = kg_compra * precio_compra
    costo_neto = costo_bruto + viaticos + fletes + otros_gastos
    ingreso_total = kg_venta * precio_venta
    utilidad_bruta = ingreso_total - costo_neto
    utilidad_neta = utilidad_bruta - retenciones - descuentos
    return utilidad_neta

def calcular_utilidad_bruta(kg_venta, precio_venta, kg_compra, precio_compra, 
                           viaticos, fletes, otros_gastos):
    """Calcula solo utilidad bruta."""
    costo_neto = (kg_compra * precio_compra) + viaticos + fletes + otros_gastos
    ingreso_total = kg_venta * precio_venta
    return ingreso_total - costo_neto

def limpiar_nombre_archivo(nombre):
    """Limpia nombre de archivo removiendo caracteres especiales."""
    nombre = unicodedata.normalize('NFKD', nombre).encode('ASCII', 'ignore').decode('utf-8')
    nombre = re.sub(r'[^\w]', '_', nombre)
    return nombre

def color_deuda(row):
    """Aplica colores a filas según estado de pago."""
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
        logger.error(f"Error al aplicar color: {e}")
    
    return [color] * len(row)

def obtener_opciones(df, columna, valores_default):
    """Obtiene lista de opciones únicas."""
    existentes = df[columna].unique().tolist() if not df.empty and columna in df.columns else []
    todas = list(set(valores_default + [x for x in existentes if x]))
    return sorted(todas)

# ==================== FUNCIONES DE BASE DE DATOS ====================

def subir_archivo(archivo, nombre_base):
    """Sube archivo a Supabase Storage."""
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
        logger.info(f"Archivo subido: {nombre_archivo}")
        return url_publica
        
    except Exception as e:
        logger.error(f"Error al subir archivo: {e}")
        st.error(f"❌ Error: {str(e)}")
        return None

@st.cache_data(ttl=CACHE_TTL_SECONDS)
def cargar_datos():
    """Carga datos desde Supabase con caché optimizado."""
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
        st.error(f"⚠️ Error al cargar configuración: {str(e)}")
    
    return df_ventas, df_gastos, saldo_inicial

# ==================== FUNCIONES DE REPORTES ====================

def generar_reporte_semanal(df_ventas, df_gastos, fecha_inicio, fecha_fin):
    """
    Genera reporte semanal automático con métricas clave.
    
    Returns:
        dict: Diccionario con métricas del reporte
    """
    reporte = {
        'periodo': f"{fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')}",
        'operaciones': 0,
        'utilidad_operaciones': 0,
        'gastos_fijos': 0,
        'utilidad_neta': 0,
        'volumen_kg': 0,
        'promedio_por_operacion': 0,
        'mejor_cliente': None,
        'mejor_dia': None,
        'alertas': []
    }
    
    if not df_ventas.empty:
        reporte['operaciones'] = len(df_ventas)
        reporte['utilidad_operaciones'] = df_ventas['Utilidad'].sum()
        reporte['volumen_kg'] = df_ventas['Kg_Venta'].sum()
        reporte['promedio_por_operacion'] = reporte['utilidad_operaciones'] / reporte['operaciones'] if reporte['operaciones'] > 0 else 0
        
        # Mejor cliente
        cliente_stats = df_ventas.groupby('Cliente')['Utilidad'].sum().sort_values(ascending=False)
        if not cliente_stats.empty:
            reporte['mejor_cliente'] = {
                'nombre': cliente_stats.index[0],
                'utilidad': cliente_stats.iloc[0]
            }
        
        # Mejor día
        df_ventas_copy = df_ventas.copy()
        df_ventas_copy['Dia'] = df_ventas_copy['Fecha'].dt.day_name()
        dia_stats = df_ventas_copy.groupby('Dia')['Utilidad'].mean().sort_values(ascending=False)
        if not dia_stats.empty:
            reporte['mejor_dia'] = {
                'nombre': dia_stats.index[0],
                'promedio': dia_stats.iloc[0]
            }
    
    if not df_gastos.empty:
        gastos = df_gastos[df_gastos['Tipo'] == 'Gasto']
        reporte['gastos_fijos'] = gastos['Monto'].sum()
    
    reporte['utilidad_neta'] = reporte['utilidad_operaciones'] - reporte['gastos_fijos']
    
    return reporte



# ==================== FUNCIONES DE ANÁLISIS DE PRECIOS HISTÓRICOS ====================

def obtener_semana_del_mes(fecha):
    """Obtiene el número de semana dentro del mes (1-5)."""
    dia = fecha.day
    return (dia - 1) // 7 + 1

def analizar_precios_historicos(df_2025, df_2026, producto="Plátano"):
    """Analiza precios históricos comparando 2025 vs 2026."""
    import numpy as np
    
    analisis = {
        'por_semana': {}, 'promedio_2025': 0, 'promedio_2026': 0,
        'diferencia_promedio': 0, 'alertas': []
    }
    
    df_2025_prod = df_2025[df_2025['producto'] == producto].copy() if not df_2025.empty else pd.DataFrame()
    df_2026_prod = df_2026[df_2026['Producto'] == producto].copy() if not df_2026.empty else pd.DataFrame()
    
    if df_2025_prod.empty and df_2026_prod.empty:
        return analisis
    
    if not df_2025_prod.empty:
        df_2025_prod['Semana'] = df_2025_prod['fecha'].apply(obtener_semana_del_mes)
        df_2025_prod['Mes'] = df_2025_prod['fecha'].dt.month
    
    if not df_2026_prod.empty:
        df_2026_prod['Semana'] = df_2026_prod['Fecha'].apply(obtener_semana_del_mes)
        df_2026_prod['Mes'] = df_2026_prod['Fecha'].dt.month
    
    for mes in range(1, 13):
        for semana in range(1, 6):
            key = f"M{mes}_S{semana}"
            precio_2025 = 0
            if not df_2025_prod.empty:
                datos_2025 = df_2025_prod[(df_2025_prod['Mes'] == mes) & (df_2025_prod['Semana'] == semana)]
                if not datos_2025.empty:
                    precio_2025 = datos_2025['precio_compra'].mean()
            
            precio_2026 = 0
            if not df_2026_prod.empty:
                datos_2026 = df_2026_prod[(df_2026_prod['Mes'] == mes) & (df_2026_prod['Semana'] == semana)]
                if not datos_2026.empty:
                    precio_2026 = datos_2026['Precio_Compra'].mean()
            
            if precio_2025 > 0 or precio_2026 > 0:
                analisis['por_semana'][key] = {
                    'mes': mes, 'semana': semana,
                    'precio_2025': precio_2025, 'precio_2026': precio_2026,
                    'diferencia': precio_2026 - precio_2025,
                    'porcentaje': ((precio_2026 - precio_2025) / precio_2025 * 100) if precio_2025 > 0 else 0
                }
    
    if not df_2025_prod.empty:
        analisis['promedio_2025'] = df_2025_prod['precio_compra'].mean()
    if not df_2026_prod.empty:
        analisis['promedio_2026'] = df_2026_prod['Precio_Compra'].mean()
    
    analisis['diferencia_promedio'] = analisis['promedio_2026'] - analisis['promedio_2025']
    
    if analisis['promedio_2025'] > 0 and analisis['promedio_2026'] > 0:
        pct_cambio = (analisis['diferencia_promedio'] / analisis['promedio_2025']) * 100
        if pct_cambio > 30:
            analisis['alertas'].append({'tipo': 'warning', 'mensaje': f"⚠️ Precio {pct_cambio:.1f}% MÁS ALTO que 2025"})
        elif pct_cambio < -20:
            analisis['alertas'].append({'tipo': 'success', 'mensaje': f"✅ Precio {abs(pct_cambio):.1f}% MÁS BAJO - Buen momento para comprar"})
        elif abs(pct_cambio) < 10:
            analisis['alertas'].append({'tipo': 'info', 'mensaje': f"ℹ️ Precio estable vs 2025 ({pct_cambio:+.1f}%)"})
    
    return analisis

@st.cache_data(ttl=CACHE_TTL_SECONDS)
def cargar_datos_2025():
    """Carga datos históricos 2025."""
    df_2025 = pd.DataFrame()
    try:
        respuesta = supabase.table("ventas_2025").select("*").order("fecha", desc=True).execute()
        df_2025 = pd.DataFrame(respuesta.data)
        if not df_2025.empty:
            df_2025['fecha'] = pd.to_datetime(df_2025['fecha'])
            campos_numericos = ['kg_compra', 'precio_compra', 'viaticos', 'fletes', 'otros_gastos',
                               'kg_venta', 'precio_venta', 'retenciones', 'descuentos', 'utilidad_neta']
            for campo in campos_numericos:
                if campo in df_2025.columns:
                    df_2025[campo] = pd.to_numeric(df_2025[campo], errors='coerce').fillna(0.0)
    except Exception as e:
        logger.error(f"Error al cargar datos 2025: {e}")
    return df_2025

@st.cache_data(ttl=CACHE_TTL_SECONDS)
def cargar_notas_precios():
    """Carga notas de precios."""
    df_notas = pd.DataFrame()
    try:
        respuesta = supabase.table("notas_precios").select("*").order("fecha", desc=True).execute()
        df_notas = pd.DataFrame(respuesta.data)
        if not df_notas.empty:
            df_notas['fecha'] = pd.to_datetime(df_notas['fecha'])
    except Exception as e:
        logger.error(f"Error al cargar notas: {e}")
    return df_notas

def guardar_nota_precio(fecha, producto, nota, tipo_evento):
    """Guarda nota sobre precios."""
    try:
        supabase.table("notas_precios").insert({
            "fecha": str(fecha), "producto": producto,
            "nota": nota, "tipo_evento": tipo_evento
        }).execute()
        cargar_notas_precios.clear()
        return True
    except Exception as e:
        logger.error(f"Error al guardar nota: {e}")
        return False


# ==================== FUNCIONES DE METAS Y OBJETIVOS ====================

@st.cache_data(ttl=CACHE_TTL_SECONDS)
def cargar_metas():
    """Carga metas mensuales desde Supabase."""
    df_metas = pd.DataFrame()
    try:
        respuesta = supabase.table("metas_mensuales").select("*").order("año", desc=True).order("mes", desc=True).execute()
        df_metas = pd.DataFrame(respuesta.data)
        if not df_metas.empty:
            df_metas['meta_utilidad'] = pd.to_numeric(df_metas['meta_utilidad'], errors='coerce').fillna(0)
            df_metas['meta_operaciones'] = pd.to_numeric(df_metas['meta_operaciones'], errors='coerce').fillna(0)
            df_metas['meta_volumen_kg'] = pd.to_numeric(df_metas['meta_volumen_kg'], errors='coerce').fillna(0)
    except Exception as e:
        logger.error(f"Error al cargar metas: {e}")
    return df_metas

def obtener_meta_mes(año, mes):
    """Obtiene la meta de un mes específico."""
    df_metas = cargar_metas()
    if df_metas.empty:
        return None
    
    meta = df_metas[(df_metas['año'] == año) & (df_metas['mes'] == mes)]
    if not meta.empty:
        return {
            'utilidad': float(meta.iloc[0]['meta_utilidad']),
            'operaciones': int(meta.iloc[0]['meta_operaciones']),
            'volumen': float(meta.iloc[0]['meta_volumen_kg']),
            'notas': meta.iloc[0].get('notas', '')
        }
    return None

def guardar_meta(año, mes, meta_utilidad, meta_operaciones, meta_volumen, notas=""):
    """Guarda o actualiza una meta mensual."""
    try:
        # Verificar si existe
        existente = supabase.table("metas_mensuales").select("id").eq("año", año).eq("mes", mes).execute()
        
        datos = {
            "año": año,
            "mes": mes,
            "meta_utilidad": meta_utilidad,
            "meta_operaciones": meta_operaciones,
            "meta_volumen_kg": meta_volumen,
            "notas": notas,
            "updated_at": datetime.now().isoformat()
        }
        
        if existente.data:
            # Actualizar
            supabase.table("metas_mensuales").update(datos).eq("año", año).eq("mes", mes).execute()
        else:
            # Insertar
            supabase.table("metas_mensuales").insert(datos).execute()
        
        cargar_metas.clear()
        return True
    except Exception as e:
        logger.error(f"Error al guardar meta: {e}")
        return False

def calcular_progreso_meta(utilidad_actual, operaciones_actuales, volumen_actual, meta):
    """Calcula el progreso hacia las metas."""
    if not meta:
        return None
    
    progreso = {
        'utilidad': {
            'actual': utilidad_actual,
            'meta': meta['utilidad'],
            'porcentaje': (utilidad_actual / meta['utilidad'] * 100) if meta['utilidad'] > 0 else 0,
            'faltante': meta['utilidad'] - utilidad_actual
        },
        'operaciones': {
            'actual': operaciones_actuales,
            'meta': meta['operaciones'],
            'porcentaje': (operaciones_actuales / meta['operaciones'] * 100) if meta['operaciones'] > 0 else 0,
            'faltante': meta['operaciones'] - operaciones_actuales
        },
        'volumen': {
            'actual': volumen_actual,
            'meta': meta['volumen'],
            'porcentaje': (volumen_actual / meta['volumen'] * 100) if meta['volumen'] > 0 else 0,
            'faltante': meta['volumen'] - volumen_actual
        }
    }
    
    return progreso


# ==================== FUNCIONES DE PREDICCIÓN CON IA ====================

import numpy as np
from datetime import timedelta

def predecir_precio_proxima_semana(df_historico, producto="Plátano"):
    """
    Predice el precio para la próxima semana usando promedio móvil y tendencia.
    """
    prediccion = {
        'precio_estimado': 0,
        'confianza': 0,
        'rango_min': 0,
        'rango_max': 0,
        'tendencia': 'estable',
        'sugerencia': ''
    }
    
    if df_historico.empty:
        return prediccion
    
    # Filtrar por producto
    df_prod = df_historico[df_historico['producto'] == producto].copy()
    
    if len(df_prod) < 4:
        return prediccion
    
    # Ordenar por fecha
    df_prod = df_prod.sort_values('fecha')
    
    # Calcular promedio móvil de últimas 4 semanas
    ultimos_precios = df_prod['precio_compra'].tail(8).values
    
    if len(ultimos_precios) < 4:
        return prediccion
    
    # Predicción simple: promedio ponderado (más peso a recientes)
    pesos = np.array([1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5])[:len(ultimos_precios)]
    precio_pred = np.average(ultimos_precios, weights=pesos)
    
    # Calcular tendencia
    if len(ultimos_precios) >= 4:
        mitad = len(ultimos_precios) // 2
        promedio_antiguo = np.mean(ultimos_precios[:mitad])
        promedio_reciente = np.mean(ultimos_precios[mitad:])
        
        diferencia_pct = ((promedio_reciente - promedio_antiguo) / promedio_antiguo) * 100
        
        if diferencia_pct > 10:
            tendencia = 'subida'
        elif diferencia_pct < -10:
            tendencia = 'bajada'
        else:
            tendencia = 'estable'
    else:
        tendencia = 'estable'
    
    # Calcular rango de confianza (±10%)
    desviacion = np.std(ultimos_precios)
    rango_min = max(0, precio_pred - desviacion)
    rango_max = precio_pred + desviacion
    
    # Confianza basada en variabilidad
    coef_variacion = (desviacion / precio_pred) * 100 if precio_pred > 0 else 100
    confianza = max(0, 100 - coef_variacion)
    
    # Generar sugerencia
    if tendencia == 'subida':
        sugerencia = f"📈 Precio en tendencia alcista (+{diferencia_pct:.1f}%). Considera comprar pronto antes que suba más."
    elif tendencia == 'bajada':
        sugerencia = f"📉 Precio en tendencia bajista ({diferencia_pct:.1f}%). Puedes esperar un poco para mejor precio."
    else:
        sugerencia = "➡️ Precio estable. Buen momento para comprar según tus necesidades."
    
    prediccion = {
        'precio_estimado': float(precio_pred),
        'confianza': float(confianza),
        'rango_min': float(rango_min),
        'rango_max': float(rango_max),
        'tendencia': tendencia,
        'sugerencia': sugerencia,
        'ultimo_precio': float(ultimos_precios[-1])
    }
    
    return prediccion

def analizar_mejor_dia_compra(df_historico, producto="Plátano"):
    """
    Analiza qué día de la semana tiene mejores precios históricamente.
    """
    analisis = {
        'mejor_dia': None,
        'precio_promedio': {},
        'sugerencia': ''
    }
    
    if df_historico.empty:
        return analisis
    
    # Filtrar por producto
    df_prod = df_historico[df_historico['producto'] == producto].copy()
    
    if df_prod.empty:
        return analisis
    
    # Agregar día de la semana
    df_prod['dia_semana'] = df_prod['fecha'].dt.day_name()
    
    # Calcular promedio por día
    precios_por_dia = df_prod.groupby('dia_semana')['precio_compra'].agg(['mean', 'count']).to_dict('index')
    
    # Filtrar días con al menos 2 operaciones
    dias_validos = {dia: datos for dia, datos in precios_por_dia.items() if datos['count'] >= 2}
    
    if not dias_validos:
        return analisis
    
    # Encontrar mejor día (menor precio)
    mejor_dia = min(dias_validos.items(), key=lambda x: x[1]['mean'])
    peor_dia = max(dias_validos.items(), key=lambda x: x[1]['mean'])
    
    # Traducir días
    dias_es = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    
    precio_promedio = {dias_es.get(dia, dia): datos['mean'] for dia, datos in dias_validos.items()}
    
    ahorro_potencial = peor_dia[1]['mean'] - mejor_dia[1]['mean']
    pct_ahorro = (ahorro_potencial / peor_dia[1]['mean']) * 100
    
    sugerencia = f"💡 Históricamente, {dias_es.get(mejor_dia[0], mejor_dia[0])} tiene mejores precios "
    sugerencia += f"(${mejor_dia[1]['mean']:,.0f}/kg promedio). "
    sugerencia += f"Ahorras hasta ${ahorro_potencial:,.0f}/kg ({pct_ahorro:.1f}%) vs {dias_es.get(peor_dia[0], peor_dia[0])}."
    
    analisis = {
        'mejor_dia': dias_es.get(mejor_dia[0], mejor_dia[0]),
        'precio_promedio': precio_promedio,
        'sugerencia': sugerencia,
        'ahorro_potencial': float(ahorro_potencial)
    }
    
    return analisis

def detectar_patrones_estacionales(df_historico, producto="Plátano"):
    """
    Detecta patrones estacionales en los precios.
    """
    patrones = {
        'meses_caros': [],
        'meses_baratos': [],
        'patron_detectado': False,
        'descripcion': ''
    }
    
    if df_historico.empty:
        return patrones
    
    df_prod = df_historico[df_historico['producto'] == producto].copy()
    
    if len(df_prod) < 12:  # Necesitamos al menos 12 operaciones
        return patrones
    
    # Agregar mes
    df_prod['mes'] = df_prod['fecha'].dt.month
    
    # Promedio por mes
    precios_por_mes = df_prod.groupby('mes')['precio_compra'].agg(['mean', 'count'])
    
    # Filtrar meses con al menos 2 operaciones
    precios_por_mes = precios_por_mes[precios_por_mes['count'] >= 2]
    
    if len(precios_por_mes) < 3:
        return patrones
    
    # Calcular promedio general
    promedio_general = precios_por_mes['mean'].mean()
    
    # Identificar meses caros (>15% sobre promedio)
    meses_caros = precios_por_mes[precios_por_mes['mean'] > promedio_general * 1.15]
    meses_baratos = precios_por_mes[precios_por_mes['mean'] < promedio_general * 0.85]
    
    meses_nombres = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                     'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    
    if not meses_caros.empty or not meses_baratos.empty:
        patrones['patron_detectado'] = True
        
        if not meses_caros.empty:
            patrones['meses_caros'] = [meses_nombres[m] for m in meses_caros.index]
        
        if not meses_baratos.empty:
            patrones['meses_baratos'] = [meses_nombres[m] for m in meses_baratos.index]
        
        descripcion = "📊 Patrones detectados: "
        if patrones['meses_caros']:
            descripcion += f"Precios altos en {', '.join(patrones['meses_caros'])}. "
        if patrones['meses_baratos']:
            descripcion += f"Precios bajos en {', '.join(patrones['meses_baratos'])}."
        
        patrones['descripcion'] = descripcion
    
    return patrones

# ==================== SEGURIDAD ====================

def verificar_password():
    """Verifica contraseña de acceso."""
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
    logger.info("Conexión a Supabase OK")
except KeyError as e:
    logger.error(f"Falta configuración: {e}")
    st.error(f"⚠️ Error de configuración: Falta {e}")
    st.stop()
except Exception as e:
    logger.error(f"Error de conexión: {e}")
    st.error(f"⚠️ Error de conexión: {str(e)}")
    st.stop()

# ==================== INTERFAZ PRINCIPAL ====================

st.markdown("# 🍌 Agrícola Montserrat")
st.markdown("### _Sistema de Gestión Integral 2026 - v3.0_")
st.divider()

# ==================== SIDEBAR ====================

st.sidebar.title("⚙️ Menú")

# Botón de tema
tema_icono = "🌙" if not st.session_state.tema_oscuro else "☀️"
tema_texto = "Modo Oscuro" if not st.session_state.tema_oscuro else "Modo Claro"
if st.sidebar.button(f"{tema_icono} {tema_texto}"):
    toggle_tema()
    st.rerun()

st.sidebar.divider()

if st.sidebar.button("🔄 Actualizar Datos"):
    cargar_datos.clear()
    cargar_datos_2025.clear()
    cargar_notas_precios.clear()
    cargar_metas.clear()
    st.rerun()

st.sidebar.divider()

# Filtros de fecha
st.sidebar.subheader("📅 Período")
fecha_inicio = st.sidebar.date_input("Desde", date(2026, 1, 1))
fecha_fin = st.sidebar.date_input("Hasta", date(2026, 12, 31))

# Cargar datos
df_ventas, df_gastos, saldo_inicial = cargar_datos()
df_2025 = cargar_datos_2025()
df_notas = cargar_notas_precios()
df_metas = cargar_metas()


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
            supabase.table("configuracion_caja").update(
                {"saldo_inicial": nueva_base}
            ).gt("id", 0).execute()
            cargar_datos.clear()
            st.success("✅ Caja ajustada")
            st.rerun()
        except Exception as e:
            logger.error(f"Error al ajustar caja: {e}")
            st.error(f"❌ Error: {str(e)}")

# ==================== FILTROS DE DATOS ====================

# ==================== FILTROS DE DATOS ====================

df_ventas_filtradas = df_ventas[
    (df_ventas['Fecha'].dt.date >= fecha_inicio) &
    (df_ventas['Fecha'].dt.date <= fecha_fin)
].copy() if not df_ventas.empty else pd.DataFrame()

df_gastos_filtrados = df_gastos[
    (df_gastos['Fecha'].dt.date >= fecha_inicio) &
    (df_gastos['Fecha'].dt.date <= fecha_fin)
].copy() if not df_gastos.empty else pd.DataFrame(
    columns=['ID', 'Fecha', 'Concepto', 'Monto', 'Tipo']
)

# ==================== ALERTAS MEJORADAS ====================

alertas_criticas = []

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
        dias_hasta_venc = (pendientes['Vence'] - hoy).dt.days
        
        # Facturas vencidas
        vencidas = pendientes[dias_hasta_venc < 0]
        if not vencidas.empty:
            total_vencido = (vencidas['Kg_Venta'] * vencidas['Precio_Venta']).sum()
            alertas_criticas.append({
                'tipo': 'error',
                'icono': '🚨',
                'titulo': 'FACTURAS VENCIDAS',
                'mensaje': f"{len(vencidas)} factura(s) vencida(s)",
                'monto': total_vencido,
                'datos': vencidas[['Cliente', 'Fecha', 'Vence']].to_dict('records')
            })
        
        # Próximas a vencer
        urgentes = pendientes[(dias_hasta_venc >= 0) & (dias_hasta_venc <= 3)]
        if not urgentes.empty:
            total_urgente = (urgentes['Kg_Venta'] * urgentes['Precio_Venta']).sum()
            alertas_criticas.append({
                'tipo': 'warning',
                'icono': '⚠️',
                'titulo': 'PRÓXIMAS A VENCER',
                'mensaje': f"{len(urgentes)} factura(s) vence(n) en ≤3 días",
                'monto': total_urgente,
                'datos': urgentes[['Cliente', 'Fecha', 'Vence']].to_dict('records')
            })

# Mostrar alertas
if alertas_criticas:
    for alerta in alertas_criticas:
        if alerta['tipo'] == 'error':
            st.error(
                f"{alerta['icono']} **{alerta['titulo']}**: {alerta['mensaje']} - "
                f"Total: ${alerta['monto']:,.0f}"
            )
        else:
            st.warning(
                f"{alerta['icono']} **{alerta['titulo']}**: {alerta['mensaje']} - "
                f"Total: ${alerta['monto']:,.0f}"
            )

# ==================== PESTAÑAS PRINCIPALES ====================

tabs = st.tabs([
    "📊 Dashboard",
    "📈 Analítica",
    "📋 Reportes",
    "📈 Precios Históricos",
    "💸 Movimientos",
    "🧮 Nueva Op.",
    "🚦 Cartera"
])

(tab_dashboard, tab_analitica, tab_reportes, tab_precios,
 tab_movimientos, tab_nueva_op, tab_cartera) = tabs

# ==================== TAB: DASHBOARD ====================

with tab_dashboard:
    st.subheader("📊 Estado Financiero")
    
    utilidad_operaciones = df_ventas_filtradas['Utilidad'].sum() if not df_ventas_filtradas.empty else 0
    gastos_periodo = df_gastos_filtrados[df_gastos_filtrados['Tipo'] == 'Gasto']['Monto'].sum() \
        if not df_gastos_filtrados.empty else 0
    utilidad_neta_final = utilidad_operaciones - gastos_periodo
    volumen_total = df_ventas_filtradas['Kg_Venta'].sum() if not df_ventas_filtradas.empty else 0
    
    # Métricas principales
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 CAJA REAL", f"${caja_sistema:,.0f}", delta="Disponible")
    col2.metric("📦 Utilidad Operaciones", f"${utilidad_operaciones:,.0f}", delta="Sin gastos fijos")
    col3.metric("💵 Utilidad Neta", f"${utilidad_neta_final:,.0f}", delta="Después de gastos")
    col4.metric("📊 Volumen", f"{volumen_total:,.1f} Kg")
    
    # Botón de exportar dashboard
    if not df_ventas_filtradas.empty:
        st.divider()
        col_exp1, col_exp2, col_exp3 = st.columns([1, 1, 2])
        with col_exp1:
            excel_dashboard = exportar_a_excel(
                df_ventas_filtradas,
                "dashboard_operaciones"
            )
            crear_boton_descarga(
                excel_dashboard,
                f"dashboard_{fecha_inicio}_{fecha_fin}.xlsx",
                "📥 Descargar Dashboard (Excel)",
                "excel"
            )
    
    if gastos_periodo > 0:
        st.divider()
        st.markdown("### 📋 Desglose de Gastos Fijos")
        
        col_a, col_b = st.columns([2, 1])
        
        with col_a:
            if not df_gastos_filtrados.empty:
                gastos_detalle = df_gastos_filtrados[
                    df_gastos_filtrados['Tipo'] == 'Gasto'
                ][['Fecha', 'Concepto', 'Monto']].copy()
                
                if not gastos_detalle.empty:
                    st.dataframe(
                        gastos_detalle.style.format({'Monto': '${:,.0f}'}),
                        use_container_width=True,
                        hide_index=True
                    )
        
        with col_b:
            st.metric(
                "Total Gastos Fijos",
                f"${gastos_periodo:,.0f}",
                delta=f"-{(gastos_periodo/utilidad_operaciones*100):.1f}% de utilidad" 
                if utilidad_operaciones > 0 else ""
            )
            
            if utilidad_operaciones > 0:
                margen = (utilidad_neta_final / utilidad_operaciones) * 100
                st.metric("Margen Neto", f"{margen:.1f}%", delta="Después de gastos fijos")
    
    st.divider()
    
    # KPIs de Rendimiento
    st.markdown("### 📊 KPIs de Rendimiento")
    
    if not df_ventas_filtradas.empty:
        num_ops = len(df_ventas_filtradas)
        util_prom_op = utilidad_operaciones / num_ops if num_ops > 0 else 0
        kg_prom_op = volumen_total / num_ops if num_ops > 0 else 0
        margen_prom = (df_ventas_filtradas['Precio_Venta'] - 
                      df_ventas_filtradas['Precio_Compra']).mean()
        
        if len(df_ventas_filtradas) > 1:
            dias_op = (df_ventas_filtradas['Fecha'].max() - 
                      df_ventas_filtradas['Fecha'].min()).days + 1
            ops_por_dia = num_ops / dias_op if dias_op > 0 else 0
        else:
            ops_por_dia = num_ops
        
        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        col_k1.metric("Utilidad/Op", f"${util_prom_op:,.0f}", 
                     help="Promedio de ganancia por viaje")
        col_k2.metric("Kg/Op", f"{kg_prom_op:,.0f} kg", 
                     help="Volumen promedio por viaje")
        col_k3.metric("Margen Unitario", f"${margen_prom:,.0f}/kg",
                     help="Diferencia promedio precio venta - compra")
        col_k4.metric("Ops/Día", f"{ops_por_dia:.1f}",
                     help=f"{num_ops} operaciones")
    
    st.divider()
    
    # Rankings
    st.markdown("### 🏆 Rankings del Período")
    
    if not df_ventas_filtradas.empty:
        col_r1, col_r2 = st.columns(2)
        
        with col_r1:
            st.markdown("**🤝 Mejores Clientes**")
            
            clientes_stats = df_ventas_filtradas.groupby('Cliente').agg({
                'Utilidad': 'sum',
                'Kg_Venta': 'sum',
                'ID': 'count'
            }).rename(columns={'ID': 'Ops'}).sort_values('Utilidad', ascending=False)
            
            clientes_stats['%'] = (clientes_stats['Utilidad'] / 
                                  utilidad_operaciones * 100).round(1)
            
            clientes_display = clientes_stats.copy()
            clientes_display['Utilidad'] = clientes_display['Utilidad'].apply(
                lambda x: f"${x:,.0f}"
            )
            clientes_display['%'] = clientes_display['%'].apply(lambda x: f"{x}%")
            
            st.dataframe(
                clientes_display[['Utilidad', 'Ops', '%']],
                use_container_width=True
            )
        
        with col_r2:
            st.markdown("**🚚 Mejores Proveedores**")
            
            prov_stats = df_ventas_filtradas.groupby('Proveedor').agg({
                'Utilidad': 'sum',
                'Kg_Compra': 'sum',
                'Precio_Compra': 'mean',
                'ID': 'count'
            }).rename(columns={'ID': 'Ops'}).sort_values('Utilidad', ascending=False)
            
            prov_display = prov_stats.copy()
            prov_display['Utilidad'] = prov_display['Utilidad'].apply(
                lambda x: f"${x:,.0f}"
            )
            prov_display['Precio_Compra'] = prov_display['Precio_Compra'].apply(
                lambda x: f"${x:,.0f}/kg"
            )
            
            st.dataframe(
                prov_display[['Utilidad', 'Ops', 'Precio_Compra']],
                use_container_width=True
            )
    
    st.divider()
    
    # Alertas y Recomendaciones
    st.markdown("### 🚨 Alertas y Recomendaciones")
    
    alertas_dash = []
    recomendaciones = []
    
    if not df_ventas_filtradas.empty:
        ops_perdida = df_ventas_filtradas[df_ventas_filtradas['Utilidad'] < 0]
        if not ops_perdida.empty:
            total_perd = ops_perdida['Utilidad'].sum()
            alertas_dash.append({
                'tipo': 'warning',
                'mensaje': f"⚠️ {len(ops_perdida)} operación(es) con pérdida: ${abs(total_perd):,.0f}"
            })
        
        if not clientes_stats.empty:
            princ_cliente = clientes_stats.iloc[0]
            if princ_cliente['%'] > 40:
                alertas_dash.append({
                    'tipo': 'info',
                    'mensaje': f"ℹ️ {princ_cliente.name} representa {princ_cliente['%']}% (concentración)"
                })
        
        if not prov_stats.empty and len(prov_stats) > 1:
            mejor_prov_idx = prov_stats['Precio_Compra'].idxmin()
            peor_prov_idx = prov_stats['Precio_Compra'].idxmax()
            
            precio_mejor = prov_stats.loc[mejor_prov_idx, 'Precio_Compra']
            precio_peor = prov_stats.loc[peor_prov_idx, 'Precio_Compra']
            
            if precio_peor > precio_mejor * 1.1:
                kg_peor = prov_stats.loc[peor_prov_idx, 'Kg_Compra']
                ahorro_pot = (precio_peor - precio_mejor) * kg_peor
                recomendaciones.append({
                    'tipo': 'success',
                    'mensaje': f"💡 Comprar más a {mejor_prov_idx} vs {peor_prov_idx} ahorraría ~${ahorro_pot:,.0f}"
                })
    
    if alertas_dash or recomendaciones:
        col_al, col_rec = st.columns(2)
        
        with col_al:
            if alertas_dash:
                for al in alertas_dash:
                    if al['tipo'] == 'warning':
                        st.warning(al['mensaje'])
                    else:
                        st.info(al['mensaje'])
        
        with col_rec:
            if recomendaciones:
                for rec in recomendaciones:
                    st.success(rec['mensaje'])
    else:
        st.info("✅ Todo se ve bien")
    
    st.divider()
    
    # Tendencias
    st.markdown("### 📈 Tendencias y Proyecciones")
    
    if not df_ventas_filtradas.empty and len(df_ventas_filtradas) >= 5:
        tendencias = df_ventas_filtradas.groupby(
            df_ventas_filtradas['Fecha'].dt.date
        ).agg({
            'Utilidad': 'sum',
            'Kg_Venta': 'sum'
        }).reset_index()
        tendencias.columns = ['Fecha', 'Utilidad', 'Kg_Venta']
        
        if len(tendencias) > 7:
            tendencias['Util_MA7'] = tendencias['Utilidad'].rolling(
                window=7,
                min_periods=1
            ).mean()
        
        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=('Utilidad Diaria', 'Volumen Diario')
        )
        
        fig.add_trace(
            go.Bar(
                x=tendencias['Fecha'],
                y=tendencias['Utilidad'],
                name='Utilidad',
                marker_color='lightgreen'
            ),
            row=1,
            col=1
        )
        
        if 'Util_MA7' in tendencias.columns:
            fig.add_trace(
                go.Scatter(
                    x=tendencias['Fecha'],
                    y=tendencias['Util_MA7'],
                    name='Promedio 7d',
                    line=dict(color='darkgreen', width=2)
                ),
                row=1,
                col=1
            )
        
        fig.add_trace(
            go.Bar(
                x=tendencias['Fecha'],
                y=tendencias['Kg_Venta'],
                name='Kg',
                marker_color='lightblue',
                showlegend=False
            ),
            row=1,
            col=2
        )
        
        fig.update_xaxes(title_text="Fecha", row=1, col=1)
        fig.update_xaxes(title_text="Fecha", row=1, col=2)
        fig.update_yaxes(title_text="Utilidad ($)", row=1, col=1)
        fig.update_yaxes(title_text="Kg", row=1, col=2)
        fig.update_layout(height=400, showlegend=True)
        
        st.plotly_chart(fig, use_container_width=True)
        
        if len(tendencias) >= 7:
            prom_diario = tendencias['Utilidad'].tail(7).mean()
            dias_rest = 30 - len(tendencias)
            
            if dias_rest > 0:
                proy_mes = utilidad_operaciones + (prom_diario * dias_rest)
                
                col_p1, col_p2 = st.columns(2)
                with col_p1:
                    st.metric(
                        "Proyección Fin Mes",
                        f"${proy_mes:,.0f}",
                        delta=f"+${prom_diario * dias_rest:,.0f} estimado",
                        help=f"Basado en prom 7d: ${prom_diario:,.0f}/día"
                    )
                
                with col_p2:
                    if utilidad_operaciones > 0:
                        pct_avance = (utilidad_operaciones / proy_mes * 100)
                        st.metric(
                            "Avance del Mes",
                            f"{pct_avance:.1f}%",
                            help=f"${utilidad_operaciones:,.0f} de ${proy_mes:,.0f}"
                        )
    
    st.divider()
    
    # Comparativa Productos
    st.markdown("### 📊 Comparativa de Productos")
    
    if not df_ventas_filtradas.empty and 'Producto' in df_ventas_filtradas.columns:
        prod_stats = df_ventas_filtradas.groupby('Producto').agg({
            'Utilidad': 'sum',
            'Kg_Venta': 'sum',
            'ID': 'count'
        }).rename(columns={'ID': 'Ops'}).sort_values('Utilidad', ascending=False)
        
        if not prod_stats.empty and len(prod_stats) > 1:
            prod_stats['Util_kg'] = prod_stats['Utilidad'] / prod_stats['Kg_Venta']
            
            col_pr1, col_pr2 = st.columns(2)
            
            with col_pr1:
                fig_prod = go.Figure(data=[
                    go.Bar(
                        x=prod_stats.index,
                        y=prod_stats['Utilidad'],
                        text=prod_stats['Utilidad'].apply(lambda x: f"${x:,.0f}"),
                        textposition='auto',
                        marker_color=['#2e7d32' if i == 0 else '#66bb6a' 
                                     for i in range(len(prod_stats))]
                    )
                ])
                fig_prod.update_layout(
                    title="Utilidad Total",
                    xaxis_title="Producto",
                    yaxis_title="$",
                    showlegend=False,
                    height=300
                )
                st.plotly_chart(fig_prod, use_container_width=True)
            
            with col_pr2:
                fig_rent = go.Figure(data=[
                    go.Bar(
                        x=prod_stats.index,
                        y=prod_stats['Util_kg'],
                        text=prod_stats['Util_kg'].apply(lambda x: f"${x:,.0f}/kg"),
                        textposition='auto',
                        marker_color=['#1565c0' if i == 0 else '#42a5f5' 
                                     for i in range(len(prod_stats))]
                    )
                ])
                fig_rent.update_layout(
                    title="Rentabilidad/Kg",
                    xaxis_title="Producto",
                    yaxis_title="$/kg",
                    showlegend=False,
                    height=300
                )
                st.plotly_chart(fig_rent, use_container_width=True)


    # ==================== SECCIÓN DE METAS Y OBJETIVOS ====================
    
    if not df_ventas_filtradas.empty:
        st.divider()
        st.markdown("### 🎯 Metas y Objetivos del Mes")
        
        # Obtener mes actual
        mes_actual = fecha_fin.month
        año_actual = fecha_fin.year
        
        # Cargar meta del mes
        meta_mes = obtener_meta_mes(año_actual, mes_actual)
        
        if meta_mes:
            # Calcular valores actuales
            util_actual = utilidad_neta_final
            ops_actuales = len(df_ventas_filtradas)
            vol_actual = volumen_total
            
            # Calcular progreso
            progreso = calcular_progreso_meta(util_actual, ops_actuales, vol_actual, meta_mes)
            
            # Mostrar métricas con progreso
            col_m1, col_m2, col_m3 = st.columns(3)
            
            with col_m1:
                pct_util = progreso['utilidad']['porcentaje']
                st.metric(
                    "🎯 Meta Utilidad",
                    f"${meta_mes['utilidad']:,.0f}",
                    delta=f"{pct_util:.1f}% completado"
                )
                st.progress(min(pct_util / 100, 1.0))
                if pct_util < 100:
                    st.caption(f"Faltan: ${progreso['utilidad']['faltante']:,.0f}")
                else:
                    st.caption("✅ ¡Meta cumplida!")
            
            with col_m2:
                pct_ops = progreso['operaciones']['porcentaje']
                st.metric(
                    "🎯 Meta Operaciones",
                    f"{meta_mes['operaciones']} ops",
                    delta=f"{pct_ops:.1f}% completado"
                )
                st.progress(min(pct_ops / 100, 1.0))
                if pct_ops < 100:
                    st.caption(f"Faltan: {int(progreso['operaciones']['faltante'])} ops")
                else:
                    st.caption("✅ ¡Meta cumplida!")
            
            with col_m3:
                pct_vol = progreso['volumen']['porcentaje']
                st.metric(
                    "🎯 Meta Volumen",
                    f"{meta_mes['volumen']:,.0f} kg",
                    delta=f"{pct_vol:.1f}% completado"
                )
                st.progress(min(pct_vol / 100, 1.0))
                if pct_vol < 100:
                    st.caption(f"Faltan: {progreso['volumen']['faltante']:,.0f} kg")
                else:
                    st.caption("✅ ¡Meta cumplida!")
            
            # Alertas de meta
            alertas_meta = []
            if pct_util < 50:
                alertas_meta.append("⚠️ Estás al 50% o menos de tu meta de utilidad")
            if pct_ops < 70:
                alertas_meta.append("⚠️ Necesitas más operaciones para cumplir la meta")
            
            if alertas_meta:
                st.divider()
                for alerta in alertas_meta:
                    st.warning(alerta)
            
            # Notas de la meta
            if meta_mes.get('notas'):
                st.info(f"📝 Nota: {meta_mes['notas']}")
        
        else:
            st.info("ℹ️ No hay meta definida para este mes. Define una abajo.")
        
        # Formulario para editar/crear meta
        with st.expander("✏️ Editar Meta del Mes"):
            with st.form("form_meta"):
                st.markdown(f"**Configurar meta para {['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'][mes_actual-1]} {año_actual}**")
                
                col_f1, col_f2, col_f3 = st.columns(3)
                
                with col_f1:
                    meta_util = st.number_input(
                        "Meta Utilidad ($)",
                        value=float(meta_mes['utilidad']) if meta_mes else 10000000.0,
                        step=100000.0,
                        format="%.0f"
                    )
                
                with col_f2:
                    meta_ops = st.number_input(
                        "Meta Operaciones",
                        value=int(meta_mes['operaciones']) if meta_mes else 30,
                        step=1
                    )
                
                with col_f3:
                    meta_vol = st.number_input(
                        "Meta Volumen (kg)",
                        value=float(meta_mes['volumen']) if meta_mes else 25000.0,
                        step=1000.0,
                        format="%.0f"
                    )
                
                notas_meta = st.text_area(
                    "Notas (opcional)",
                    value=meta_mes.get('notas', '') if meta_mes else '',
                    placeholder="Ej: Meta agresiva por temporada alta"
                )
                
                if st.form_submit_button("💾 Guardar Meta"):
                    if guardar_meta(año_actual, mes_actual, meta_util, meta_ops, meta_vol, notas_meta):
                        st.success("✅ Meta guardada exitosamente")
                        st.rerun()
                    else:
                        st.error("❌ Error al guardar meta")


# ==================== TAB: ANALÍTICA ====================

with tab_analitica:
    st.subheader("📈 Análisis Financiero")
    
    # Flujo de Utilidades
    st.markdown("### 💰 Flujo de Utilidades")
    
    if not df_ventas_filtradas.empty:
        col_f1, col_f2, col_f3 = st.columns(3)
        
        util_ops = df_ventas_filtradas['Utilidad'].sum()
        gtos_fij = df_gastos_filtrados[df_gastos_filtrados['Tipo'] == 'Gasto']['Monto'].sum() \
            if not df_gastos_filtrados.empty else 0
        util_fin = util_ops - gtos_fij
        
        with col_f1:
            st.metric(
                "1️⃣ Utilidad Operaciones",
                f"${util_ops:,.0f}",
                help="Ganancia de operaciones"
            )
        
        with col_f2:
            st.metric(
                "2️⃣ Gastos Fijos",
                f"-${gtos_fij:,.0f}",
                delta=f"{(gtos_fij/util_ops*100):.1f}%" if util_ops > 0 else "",
                delta_color="inverse",
                help="Nómina + gastos"
            )
        
        with col_f3:
            st.metric(
                "3️⃣ Utilidad Neta",
                f"${util_fin:,.0f}",
                delta=f"{(util_fin/util_ops*100):.1f}% margen" if util_ops > 0 else "",
                help="Ganancia real"
            )
        
        # Gráfico Waterfall
        fig_water = go.Figure(go.Waterfall(
            name="Flujo",
            orientation="v",
            measure=["relative", "relative", "total"],
            x=["Utilidad<br>Ops", "Gastos<br>Fijos", "Utilidad<br>Neta"],
            y=[util_ops, -gtos_fij, util_fin],
            text=[f"${util_ops:,.0f}", f"-${gtos_fij:,.0f}", f"${util_fin:,.0f}"],
            textposition="outside",
            connector={"line":{"color":"rgb(63, 63, 63)"}},
        ))
        
        fig_water.update_layout(
            title="Flujo de Utilidad",
            showlegend=False,
            height=400
        )
        st.plotly_chart(fig_water, use_container_width=True)
        
        st.divider()
    
    # Análisis de Precios
    st.markdown("### 📊 Análisis de Precios")
    
    if not df_ventas_filtradas.empty:
        df_precios = df_ventas_filtradas[
            df_ventas_filtradas['Precio_Plaza'] > 0
        ].sort_values("Fecha")
        
        col_g, col_m = st.columns([3, 1])
        
        with col_g:
            if not df_precios.empty:
                fig = px.line(
                    df_precios,
                    x='Fecha',
                    y=['Precio_Compra', 'Precio_Plaza'],
                    markers=True,
                    title="Evolución: Precio Compra vs Plaza"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Faltan datos de plaza")
        
        with col_m:
            if not df_precios.empty:
                plaza_prom = df_precios['Precio_Plaza'].mean()
                compra_prom = df_precios['Precio_Compra'].mean()
                ahorro_prom = plaza_prom - compra_prom
                
                st.metric(
                    "Margen vs Plaza",
                    f"${ahorro_prom:,.0f}",
                    delta="Ahorro/Kg" if ahorro_prom > 0 else "Sobrecosto"
                )
                
                if ahorro_prom > 0:
                    ahorro_tot = ahorro_prom * df_precios['Kg_Compra'].sum()
                    st.metric(
                        "Ahorro Total",
                        f"${ahorro_tot:,.0f}",
                        help="vs precio plaza"
                    )
    
    # Botón exportar analítica
    if not df_ventas_filtradas.empty:
        st.divider()
        excel_analitica = exportar_a_excel(df_ventas_filtradas, "analitica")
        crear_boton_descarga(
            excel_analitica,
            f"analitica_{fecha_inicio}_{fecha_fin}.xlsx",
            "📥 Descargar Análisis (Excel)",
            "excel"
        )

# ==================== TAB: REPORTES ====================

with tab_reportes:
    st.subheader("📋 Reportes Automáticos")
    
    st.markdown("""
    Esta sección genera reportes semanales y mensuales automáticos con métricas clave,
    comparativas históricas y análisis de tendencias.
    """)
    
    st.divider()
    
    # Selector de tipo de reporte
    tipo_reporte = st.selectbox(
        "Tipo de Reporte",
        ["Semanal", "Mensual", "Comparativo 2025 vs 2026"]
    )
    
    if tipo_reporte == "Semanal":
        st.markdown("### 📊 Reporte Semanal")
        
        # Generar reporte
        reporte = generar_reporte_semanal(
            df_ventas_filtradas,
            df_gastos_filtrados,
            fecha_inicio,
            fecha_fin
        )
        
        # Mostrar métricas
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Operaciones", reporte['operaciones'])
            st.metric("Volumen", f"{reporte['volumen_kg']:,.0f} kg")
        with col2:
            st.metric("Utilidad Ops", f"${reporte['utilidad_operaciones']:,.0f}")
            st.metric("Gastos Fijos", f"${reporte['gastos_fijos']:,.0f}")
        with col3:
            st.metric("Utilidad Neta", f"${reporte['utilidad_neta']:,.0f}")
            st.metric("Promedio/Op", f"${reporte['promedio_por_operacion']:,.0f}")
        
        st.divider()
        
        # Detalles adicionales
        if reporte['mejor_cliente']:
            st.success(
                f"🏆 Mejor Cliente: **{reporte['mejor_cliente']['nombre']}** "
                f"(${reporte['mejor_cliente']['utilidad']:,.0f})"
            )
        
        if reporte['mejor_dia']:
            st.info(
                f"📅 Mejor Día: **{reporte['mejor_dia']['nombre']}** "
                f"(${reporte['mejor_dia']['promedio']:,.0f} promedio)"
            )
    
    elif tipo_reporte == "Comparativo 2025 vs 2026":
        st.markdown("### 📊 Comparativa Histórica: 2025 vs 2026")
        
        # Obtener mes actual
        mes_actual = fecha_inicio.month
        nombre_mes = [
            'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
        ][mes_actual - 1]
        
        # Datos 2026
        util_2026 = df_ventas_filtradas['Utilidad'].sum()
        ops_2026 = len(df_ventas_filtradas)
        
        # Datos 2025
        util_2025 = DATOS_2025_MESES.get(mes_actual, 0)
        
        # Comparativa
        st.markdown(f"#### {nombre_mes}: 2025 vs 2026")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                f"{nombre_mes} 2025",
                f"${util_2025:,.0f}",
                help="Utilidad total del mismo mes año pasado"
            )
        
        with col2:
            st.metric(
                f"{nombre_mes} 2026",
                f"${util_2026:,.0f}",
                delta=f"{((util_2026 - util_2025) / util_2025 * 100):.1f}%" 
                if util_2025 > 0 else "N/A",
                help="Utilidad total del mes actual"
            )
        
        with col3:
            diferencia = util_2026 - util_2025
            st.metric(
                "Diferencia",
                f"${abs(diferencia):,.0f}",
                delta="Mejor" if diferencia > 0 else "Peor",
                delta_color="normal" if diferencia > 0 else "inverse"
            )
        
        st.divider()
        
        # Gráfico comparativo
        st.markdown("#### Comparativa Mensual 2025 vs 2026")
        
        # Preparar datos para gráfico
        meses_nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 
                        'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        
        # Calcular utilidad por mes 2026
        if not df_ventas.empty:
            df_ventas_2026 = df_ventas.copy()
            df_ventas_2026['Mes'] = df_ventas_2026['Fecha'].dt.month
            util_2026_meses = df_ventas_2026.groupby('Mes')['Utilidad'].sum().to_dict()
        else:
            util_2026_meses = {}
        
        # Datos para gráfico
        datos_2025 = [DATOS_2025_MESES.get(i, 0) for i in range(1, 13)]
        datos_2026 = [util_2026_meses.get(i, 0) for i in range(1, 13)]
        
        fig_comp = go.Figure()
        
        fig_comp.add_trace(go.Bar(
            x=meses_nombres,
            y=datos_2025,
            name='2025',
            marker_color='lightblue'
        ))
        
        fig_comp.add_trace(go.Bar(
            x=meses_nombres,
            y=datos_2026,
            name='2026',
            marker_color='lightgreen'
        ))
        
        fig_comp.update_layout(
            title="Utilidad Mensual: 2025 vs 2026",
            xaxis_title="Mes",
            yaxis_title="Utilidad ($)",
            barmode='group',
            height=400
        )
        
        st.plotly_chart(fig_comp, use_container_width=True)
        
        st.divider()
        
        # Resumen anual
        st.markdown("#### Resumen Anual")
        
        total_2026_anual = sum(datos_2026)
        
        col_a1, col_a2, col_a3 = st.columns(3)
        
        with col_a1:
            st.metric(
                "Total 2025",
                f"${TOTAL_2025:,.0f}",
                help="322 operaciones"
            )
        
        with col_a2:
            st.metric(
                "Total 2026 (a la fecha)",
                f"${total_2026_anual:,.0f}",
                help=f"{len(df_ventas)} operaciones"
            )
        
        with col_a3:
            if total_2026_anual > 0:
                proy_2026 = (TOTAL_2025 / TOTAL_OPERACIONES_2025) * len(df_ventas)
                st.metric(
                    "Proyección 2026",
                    f"${proy_2026:,.0f}",
                    delta=f"{((proy_2026 - TOTAL_2025) / TOTAL_2025 * 100):.1f}%",
                    help="Proyección basada en ritmo actual"
                )
    
    # Botón de exportar reporte
    if not df_ventas_filtradas.empty:
        st.divider()
        excel_reporte = exportar_a_excel(df_ventas_filtradas, "reporte")
        crear_boton_descarga(
            excel_reporte,
            f"reporte_{tipo_reporte}_{fecha_inicio}_{fecha_fin}.xlsx",
            f"📥 Descargar Reporte {tipo_reporte} (Excel)",
            "excel"
        )

# ==================== TAB: MOVIMIENTOS ====================

with tab_movimientos:
    st.subheader("💸 Registro de Movimientos")
    
    with st.form("add_movimiento", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns(4)
        
        fecha_mov = col1.date_input("Fecha", date.today())
        concepto_mov = col2.text_input("Concepto")
        tipo_mov = col3.selectbox(
            "Tipo",
            ["Gasto (Gasolina/Nómina)", "Préstamo Salida", "Ingreso Extra"]
        )
        monto_mov = col4.number_input("Valor ($)", min_value=0.0, format="%.2f")
        
        if st.form_submit_button("💾 Registrar"):
            tipo_db = "Gasto"
            if "Préstamo" in tipo_mov:
                tipo_db = "Préstamo Salida"
            elif "Ingreso" in tipo_mov:
                tipo_db = "Ingreso Extra"
            
            if not concepto_mov:
                st.error("❌ El concepto es obligatorio")
            elif monto_mov <= 0:
                st.error("❌ El monto debe ser > 0")
            else:
                try:
                    supabase.table("gastos_fijos_2026").insert({
                        "fecha": str(fecha_mov),
                        "concepto": concepto_mov,
                        "monto": monto_mov,
                        "tipo": tipo_db
                    }).execute()
                    cargar_datos.clear()
                    st.success("✅ Registrado")
                    st.rerun()
                except Exception as e:
                    logger.error(f"Error: {e}")
                    st.error(f"❌ Error: {str(e)}")
    
    if not df_gastos_filtrados.empty:
        st.dataframe(
            df_gastos_filtrados.style.format({"Monto": "${:,.2f}"}),
            use_container_width=True,
            hide_index=True
        )
        
        # Exportar movimientos
        st.divider()
        col_exp1, col_exp2 = st.columns([1, 3])
        with col_exp1:
            excel_mov = exportar_a_excel(df_gastos_filtrados, "movimientos")
            crear_boton_descarga(
                excel_mov,
                f"movimientos_{fecha_inicio}_{fecha_fin}.xlsx",
                "📥 Exportar Movimientos",
                "excel"
            )
        
        with st.expander("🗑️ Borrar Movimiento"):
            id_borrar = st.number_input("ID a borrar", step=1, min_value=1)
            if st.button("Eliminar"):
                try:
                    supabase.table("gastos_fijos_2026").delete().eq("id", id_borrar).execute()
                    cargar_datos.clear()
                    st.success("✅ Eliminado")
                    st.rerun()
                except Exception as e:
                    logger.error(f"Error: {e}")
                    st.error(f"❌ Error: {str(e)}")

# ==================== TAB: NUEVA OPERACIÓN ====================

with tab_nueva_op:
    with st.form("add_viaje", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns(4)
        
        fecha_op = col1.date_input("Fecha", date.today())
        producto = col2.selectbox(
            "Fruta",
            obtener_opciones(df_ventas, 'Producto', ["Plátano", "Guayabo"])
        )
        nuevo_prod = col2.text_input("¿Otra fruta?", placeholder="Opcional", key="nuevo_producto")
        proveedor = col3.selectbox(
            "Proveedor",
            obtener_opciones(df_ventas, 'Proveedor', ["Omar", "Rancho"])
        )
        nuevo_prov = col3.text_input("¿Otro proveedor?", placeholder="Opcional", key="nuevo_proveedor")
        cliente = col4.selectbox(
            "Cliente",
            obtener_opciones(df_ventas, 'Cliente', ["Calima", "Fogón del Mar"])
        )
        nuevo_cli = col4.text_input("¿Otro cliente?", placeholder="Opcional", key="nuevo_cliente")
        
        col_compra, col_venta = st.columns(2)
        
        with col_compra:
            st.markdown("##### 🛒 Compra")
            kg_c = st.number_input("Kg Compra", min_value=0.0, format="%.2f")
            pc = st.number_input("Precio Compra ($/kg)", min_value=0.0, format="%.2f")
            pp = st.number_input("Precio Plaza ($/kg)", min_value=0.0, format="%.2f")
            
            st.markdown("**Costos Adicionales**")
            cc1, cc2, cc3 = st.columns(3)
            viat = cc1.number_input("Viáticos", min_value=0.0, format="%.2f")
            flet = cc2.number_input("Fletes", min_value=0.0, format="%.2f")
            otros = cc3.number_input("Otros", min_value=0.0, format="%.2f")
            
            file_c = st.file_uploader("Factura Compra", type=list(ALLOWED_FILE_EXTENSIONS))
        
        with col_venta:
            st.markdown("##### 🤝 Venta")
            kg_v = st.number_input("Kg Venta", min_value=0.0, format="%.2f")
            pv = st.number_input("Precio Venta ($/kg)", min_value=0.0, format="%.2f")
            
            st.markdown("**Deducciones**")
            cv1, cv2 = st.columns(2)
            ret = cv1.number_input("Retenciones", min_value=0.0, format="%.2f")
            desc = cv2.number_input("Descuentos", min_value=0.0, format="%.2f")
            
            file_v = st.file_uploader("Factura Venta", type=list(ALLOWED_FILE_EXTENSIONS))
        
        # Cálculos
        ub = calcular_utilidad_bruta(kg_v, pv, kg_c, pc, viat, flet, otros)
        un = calcular_utilidad_neta(kg_v, pv, kg_c, pc, viat, flet, otros, ret, desc)
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            cn = (kg_c * pc) + viat + flet + otros
            st.info(f"💵 Costo Neto: ${cn:,.0f}")
            if ub >= 0:
                st.success(f"📊 Utilidad Bruta: ${ub:,.0f}")
            else:
                st.error(f"📊 Pérdida Bruta: ${abs(ub):,.0f}")
        
        with col_c2:
            if un >= 0:
                st.success(f"💰 Utilidad Neta: ${un:,.0f}")
            else:
                st.error(f"⚠️ Pérdida Neta: ${abs(un):,.0f}")
        
        est = st.selectbox("Estado", ["Pagado", "Pendiente"])
        dias = st.number_input("Días Crédito", value=DEFAULT_CREDITO_DIAS, min_value=0)
        
        if st.form_submit_button("💾 Guardar Operación"):
            prod_f = nuevo_prod or producto
            prov_f = nuevo_prov or proveedor
            cli_f = nuevo_cli or cliente
            
            es_val, advs, errs = validar_operacion_comercial(
                kg_c, pc, kg_v, pv, viat, flet, otros, ret, desc
            )
            
            if errs:
                for err in errs:
                    st.error(f"❌ {err}")
            
            if advs:
                for adv in advs:
                    st.warning(adv)
            
            if es_val and prov_f and cli_f:
                with st.spinner("Guardando..."):
                    try:
                        url_c = subir_archivo(file_c, f"c_{prov_f}")
                        url_v = subir_archivo(file_v, f"v_{cli_f}")
                        
                        datos = {
                            "fecha": str(fecha_op),
                            "producto": prod_f,
                            "proveedor": prov_f,
                            "cliente": cli_f,
                            "kg_compra": kg_c,
                            "precio_compra": pc,
                            "viaticos": viat,
                            "fletes": flet,
                            "otros_gastos": otros,
                            "kg_venta": kg_v,
                            "precio_venta": pv,
                            "retenciones": ret,
                            "descuentos": desc,
                            "utilidad": un,
                            "estado_pago": est,
                            "dias_credito": dias,
                            "precio_plaza": pp,
                            "fec_doc_url": url_c if url_c else "",
                            "fev_doc_url": url_v if url_v else ""
                        }
                        
                        supabase.table("ventas_2026").insert(datos).execute()
                        cargar_datos.clear()
                        st.success("✅ Registrado!")
                        st.rerun()
                        
                    except Exception as e:
                        logger.error(f"Error: {e}")
                        st.error(f"❌ Error: {str(e)}")
            elif not prov_f or not cli_f:
                st.error("❌ Proveedor y Cliente obligatorios")

# ==================== TAB: CARTERA ====================

with tab_cartera:
    if not df_ventas_filtradas.empty:
        config_cols = {
            "FEC_Doc": st.column_config.LinkColumn("F.C", display_text="Ver"),
            "FEV_Doc": st.column_config.LinkColumn("F.V", display_text="Ver"),
            "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "Utilidad": st.column_config.NumberColumn("Utilidad Neta", format="$%d"),
        }
        
        # Exportar cartera
        st.markdown("### 🚦 Cartera de Clientes")
        col_exp1, col_exp2 = st.columns([1, 3])
        with col_exp1:
            excel_cart = exportar_a_excel(df_ventas_filtradas, "cartera")
            crear_boton_descarga(
                excel_cart,
                f"cartera_{fecha_inicio}_{fecha_fin}.xlsx",
                "📥 Exportar Cartera",
                "excel"
            )
        
        st.divider()
        
        evt = st.dataframe(
            df_ventas_filtradas.style.apply(color_deuda, axis=1),
            use_container_width=True,
            column_config=config_cols,
            selection_mode="single-row",
            on_select="rerun",
            hide_index=True
        )
        
        if evt.selection.rows:
            fila = df_ventas_filtradas.iloc[evt.selection.rows[0]]
            st.divider()
            st.markdown(
                f"### ✏️ Editando: **{fila['Fecha'].strftime('%d-%b')}** - {fila['Cliente']}"
            )
            
            with st.form("edit_full"):
                col1, col2, col3, col4 = st.columns(4)
                
                e_fecha = col1.date_input("Fecha", value=pd.to_datetime(fila['Fecha']).date())
                e_cli = col2.text_input("Cliente", value=fila['Cliente'])
                e_prov = col3.text_input("Proveedor", value=fila['Proveedor'])
                e_prod = col4.text_input("Producto", value=fila['Producto'])
                
                st.markdown("**Datos Compra**")
                cc1, cc2, cc3 = st.columns(3)
                e_kgc = cc1.number_input("Kg Compra", value=float(fila['Kg_Compra']), format="%.2f")
                e_pc = cc2.number_input("Precio Compra", value=float(fila['Precio_Compra']), format="%.2f")
                e_pp = cc3.number_input("Precio Plaza", value=float(fila['Precio_Plaza']), format="%.2f")
                
                st.markdown("**Costos Adicionales**")
                cc4, cc5, cc6 = st.columns(3)
                e_viat = cc4.number_input("Viáticos", value=float(fila.get('Viaticos', 0.0)), format="%.2f")
                e_flet = cc5.number_input("Fletes", value=float(fila.get('Fletes', 0.0)), format="%.2f")
                e_otros = cc6.number_input("Otros", value=float(fila.get('Otros_Gastos', 0.0)), format="%.2f")
                
                st.markdown("**Datos Venta**")
                cv1, cv2, cv3, cv4 = st.columns(4)
                e_kgv = cv1.number_input("Kg Venta", value=float(fila['Kg_Venta']), format="%.2f")
                e_pv = cv2.number_input("Precio Venta", value=float(fila['Precio_Venta']), format="%.2f")
                e_ret = cv3.number_input("Retenciones", value=float(fila.get('Retenciones', 0.0)), format="%.2f")
                e_desc = cv4.number_input("Descuentos", value=float(fila.get('Descuentos', 0.0)), format="%.2f")
                
                e_est = st.selectbox(
                    "Estado",
                    ["Pagado", "Pendiente"],
                    index=0 if fila['Estado_Pago'] == "Pagado" else 1
                )
                
                st.markdown("**Soportes**")
                cf1, cf2 = st.columns(2)
                nf_c = cf1.file_uploader("Nueva F.Compra", type=list(ALLOWED_FILE_EXTENSIONS))
                nf_v = cf2.file_uploader("Nueva F.Venta", type=list(ALLOWED_FILE_EXTENSIONS))
                
                if st.form_submit_button("💾 Guardar"):
                    es_val, advs, errs = validar_operacion_comercial(
                        e_kgc, e_pc, e_kgv, e_pv, e_viat, e_flet, e_otros, e_ret, e_desc
                    )
                    
                    if errs:
                        for err in errs:
                            st.error(f"❌ {err}")
                    
                    if advs:
                        for adv in advs:
                            st.warning(adv)
                    
                    if es_val:
                        try:
                            nu = calcular_utilidad_neta(
                                e_kgv, e_pv, e_kgc, e_pc, e_viat, e_flet, e_otros, e_ret, e_desc
                            )
                            
                            acts = {
                                "fecha": str(e_fecha),
                                "cliente": e_cli,
                                "proveedor": e_prov,
                                "producto": e_prod,
                                "kg_compra": e_kgc,
                                "precio_compra": e_pc,
                                "precio_plaza": e_pp,
                                "viaticos": e_viat,
                                "fletes": e_flet,
                                "otros_gastos": e_otros,
                                "kg_venta": e_kgv,
                                "precio_venta": e_pv,
                                "retenciones": e_ret,
                                "descuentos": e_desc,
                                "estado_pago": e_est,
                                "utilidad": nu
                            }
                            
                            if nf_c:
                                u = subir_archivo(nf_c, f"e_c_{e_prov}")
                                if u:
                                    acts["fec_doc_url"] = u
                            
                            if nf_v:
                                u = subir_archivo(nf_v, f"e_v_{e_cli}")
                                if u:
                                    acts["fev_doc_url"] = u
                            
                            supabase.table("ventas_2026").update(acts).eq(
                                "id", int(fila['ID'])
                            ).execute()
                            
                            cargar_datos.clear()
                            st.success("✅ Actualizado")
                            st.rerun()
                            
                        except Exception as e:
                            logger.error(f"Error: {e}")
                            st.error(f"❌ Error: {str(e)}")
            
            if st.button("🗑️ Borrar"):
                try:
                    supabase.table("ventas_2026").delete().eq("id", int(fila['ID'])).execute()
                    cargar_datos.clear()
                    st.success("✅ Eliminado")
                    st.rerun()
                except Exception as e:
                    logger.error(f"Error: {e}")
                    st.error(f"❌ Error: {str(e)}")


# ==================== TAB: PRECIOS HISTÓRICOS ====================

with tab_precios:
    st.subheader("📈 Análisis de Precios Históricos")
    
    st.markdown("""
    Compara precios históricos entre 2025 y 2026 para anticiparte a las fluctuaciones 
    del mercado y tomar mejores decisiones de compra.
    """)
    
    st.divider()
    
    # Selector de producto
    productos_disponibles = []
    if not df_ventas.empty:
        productos_disponibles = df_ventas['Producto'].unique().tolist()
    if not df_2025.empty:
        productos_2025 = df_2025['producto'].unique().tolist()
        productos_disponibles = list(set(productos_disponibles + productos_2025))
    
    if not productos_disponibles:
        st.warning("⚠️ No hay datos de productos disponibles")
    else:
        col_sel1, col_sel2 = st.columns([1, 3])
        
        with col_sel1:
            producto_seleccionado = st.selectbox(
                "Producto",
                sorted(productos_disponibles),
                index=0 if "Plátano" in productos_disponibles else 0
            )
        
        with col_sel2:
            st.info(f"📊 Analizando: **{producto_seleccionado}**")
        
        # Análisis
        analisis = analizar_precios_historicos(df_2025, df_ventas_filtradas, producto_seleccionado)
        
        # Métricas
        st.markdown("### 💰 Resumen de Precios")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Promedio 2025",
                f"${analisis['promedio_2025']:,.0f}/kg" if analisis['promedio_2025'] > 0 else "Sin datos"
            )
        
        with col2:
            st.metric(
                "Promedio 2026",
                f"${analisis['promedio_2026']:,.0f}/kg" if analisis['promedio_2026'] > 0 else "Sin datos",
                delta=f"${analisis['diferencia_promedio']:,.0f}" if analisis['diferencia_promedio'] != 0 else None
            )
        
        with col3:
            if analisis['promedio_2025'] > 0 and analisis['promedio_2026'] > 0:
                pct_cambio = (analisis['diferencia_promedio'] / analisis['promedio_2025']) * 100
                st.metric(
                    "Variación",
                    f"{pct_cambio:+.1f}%",
                    delta="Aumento" if pct_cambio > 0 else "Reducción",
                    delta_color="inverse" if pct_cambio > 0 else "normal"
                )
        
        # Alertas
        if analisis['alertas']:
            st.divider()
            for alerta in analisis['alertas']:
                if alerta['tipo'] == 'warning':
                    st.warning(alerta['mensaje'])
                elif alerta['tipo'] == 'success':
                    st.success(alerta['mensaje'])
                else:
                    st.info(alerta['mensaje'])
        
        st.divider()
        
        # Gráfico
        st.markdown("### 📊 Evolución Semanal")
        
        if analisis['por_semana']:
            datos_grafico = []
            meses_nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 
                            'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
            
            for key, datos in sorted(analisis['por_semana'].items()):
                mes_nombre = meses_nombres[datos['mes'] - 1]
                semana = datos['semana']
                
                if datos['precio_2025'] > 0:
                    datos_grafico.append({
                        'Periodo': f"{mes_nombre} S{semana}",
                        'Precio': datos['precio_2025'],
                        'Año': '2025'
                    })
                
                if datos['precio_2026'] > 0:
                    datos_grafico.append({
                        'Periodo': f"{mes_nombre} S{semana}",
                        'Precio': datos['precio_2026'],
                        'Año': '2026'
                    })
            
            if datos_grafico:
                df_grafico = pd.DataFrame(datos_grafico)
                
                fig = go.Figure()
                
                df_2025_graf = df_grafico[df_grafico['Año'] == '2025']
                if not df_2025_graf.empty:
                    fig.add_trace(go.Scatter(
                        x=df_2025_graf['Periodo'],
                        y=df_2025_graf['Precio'],
                        name='2025',
                        mode='lines+markers',
                        line=dict(color='#42a5f5', width=3),
                        marker=dict(size=8)
                    ))
                
                df_2026_graf = df_grafico[df_grafico['Año'] == '2026']
                if not df_2026_graf.empty:
                    fig.add_trace(go.Scatter(
                        x=df_2026_graf['Periodo'],
                        y=df_2026_graf['Precio'],
                        name='2026',
                        mode='lines+markers',
                        line=dict(color='#66bb6a', width=3),
                        marker=dict(size=8)
                    ))
                
                # Agregar notas si existen
                if not df_notas.empty:
                    notas_producto = df_notas[df_notas['producto'] == producto_seleccionado]
                    for idx, nota in notas_producto.iterrows():
                        mes = nota['fecha'].month
                        semana = obtener_semana_del_mes(nota['fecha'])
                        periodo_nota = f"{meses_nombres[mes-1]} S{semana}"
                        
                        precio_periodo = df_2026_graf[df_2026_graf['Periodo'] == periodo_nota]
                        if not precio_periodo.empty:
                            fig.add_annotation(
                                x=periodo_nota,
                                y=precio_periodo['Precio'].iloc[0],
                                text=f"📝 {nota['nota'][:20]}...",
                                showarrow=True,
                                arrowhead=2,
                                bgcolor="#fff3cd",
                                bordercolor="#ff6b6b"
                            )
                
                fig.update_layout(
                    title=f"Precios: {producto_seleccionado}",
                    xaxis_title="Periodo",
                    yaxis_title="Precio ($/kg)",
                    height=500
                )
                
                st.plotly_chart(fig, use_container_width=True)
        
        st.divider()
        
        # Tabla comparativa
        st.markdown("### 📋 Tabla Comparativa")
        
        if analisis['por_semana']:
            datos_tabla = []
            meses_nombres = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
            
            for key, datos in sorted(analisis['por_semana'].items()):
                if datos['precio_2025'] > 0 or datos['precio_2026'] > 0:
                    datos_tabla.append({
                        'Mes': meses_nombres[datos['mes'] - 1],
                        'Semana': f"S{datos['semana']}",
                        '2025': f"${datos['precio_2025']:,.0f}" if datos['precio_2025'] > 0 else "-",
                        '2026': f"${datos['precio_2026']:,.0f}" if datos['precio_2026'] > 0 else "-",
                        'Dif': f"${datos['diferencia']:+,.0f}" if datos['precio_2025'] > 0 and datos['precio_2026'] > 0 else "-",
                        '%': f"{datos['porcentaje']:+.1f}%" if datos['porcentaje'] != 0 else "-"
                    })
            
            if datos_tabla:
                st.dataframe(pd.DataFrame(datos_tabla), use_container_width=True, hide_index=True)
        
        st.divider()
        

        # ==================== PREDICCIÓN CON IA ====================
        
        st.divider()
        st.markdown("### 🤖 Predicción Inteligente de Precios")
        
        # Combinar datos 2025 y 2026 para predicción
        df_completo = pd.DataFrame()
        
        if not df_2025.empty:
            df_2025_temp = df_2025[['fecha', 'producto', 'precio_compra']].copy()
            df_completo = df_2025_temp
        
        if not df_ventas.empty:
            df_2026_temp = df_ventas[['Fecha', 'Producto', 'Precio_Compra']].copy()
            df_2026_temp.columns = ['fecha', 'producto', 'precio_compra']
            df_completo = pd.concat([df_completo, df_2026_temp], ignore_index=True)
        
        if not df_completo.empty:
            # Predicción de precio próxima semana
            prediccion = predecir_precio_proxima_semana(df_completo, producto_seleccionado)
            
            if prediccion['precio_estimado'] > 0:
                st.markdown("#### 📈 Predicción para Próxima Semana")
                
                col_p1, col_p2, col_p3 = st.columns(3)
                
                with col_p1:
                    st.metric(
                        "Precio Estimado",
                        f"${prediccion['precio_estimado']:,.0f}/kg",
                        delta=f"${prediccion['precio_estimado'] - prediccion['ultimo_precio']:+,.0f} vs último"
                    )
                
                with col_p2:
                    st.metric(
                        "Rango Esperado",
                        f"${prediccion['rango_min']:,.0f} - ${prediccion['rango_max']:,.0f}",
                        help="Rango de precios probable"
                    )
                
                with col_p3:
                    # Emoji de tendencia
                    tendencia_emoji = {"subida": "📈", "bajada": "📉", "estable": "➡️"}
                    st.metric(
                        "Tendencia",
                        prediccion['tendencia'].title(),
                        delta=f"{prediccion['confianza']:.0f}% confianza"
                    )
                
                # Sugerencia
                if prediccion['tendencia'] == 'subida':
                    st.warning(prediccion['sugerencia'])
                elif prediccion['tendencia'] == 'bajada':
                    st.success(prediccion['sugerencia'])
                else:
                    st.info(prediccion['sugerencia'])
            
            st.divider()
            
            # Mejor día para comprar
            analisis_dias = analizar_mejor_dia_compra(df_completo, producto_seleccionado)
            
            if analisis_dias['mejor_dia']:
                st.markdown("#### 📅 Mejor Día para Comprar")
                
                col_d1, col_d2 = st.columns([2, 1])
                
                with col_d1:
                    st.success(analisis_dias['sugerencia'])
                    
                    # Gráfico de precios por día
                    if analisis_dias['precio_promedio']:
                        df_dias = pd.DataFrame([
                            {'Día': dia, 'Precio': precio}
                            for dia, precio in analisis_dias['precio_promedio'].items()
                        ])
                        
                        fig_dias = go.Figure(data=[
                            go.Bar(
                                x=df_dias['Día'],
                                y=df_dias['Precio'],
                                text=df_dias['Precio'].apply(lambda x: f"${x:,.0f}"),
                                textposition='auto',
                                marker_color=['#66bb6a' if dia == analisis_dias['mejor_dia'] else '#90caf9' 
                                             for dia in df_dias['Día']]
                            )
                        ])
                        
                        fig_dias.update_layout(
                            title="Precio Promedio por Día de la Semana",
                            xaxis_title="Día",
                            yaxis_title="Precio ($/kg)",
                            height=300,
                            showlegend=False
                        )
                        
                        st.plotly_chart(fig_dias, use_container_width=True)
                
                with col_d2:
                    st.metric(
                        "Mejor Día",
                        analisis_dias['mejor_dia'],
                        delta=f"-${analisis_dias['ahorro_potencial']:,.0f}/kg",
                        help="Ahorro potencial vs día más caro"
                    )
            
            st.divider()
            
            # Patrones estacionales
            patrones = detectar_patrones_estacionales(df_completo, producto_seleccionado)
            
            if patrones['patron_detectado']:
                st.markdown("#### 🔄 Patrones Estacionales Detectados")
                
                col_pat1, col_pat2 = st.columns(2)
                
                with col_pat1:
                    if patrones['meses_caros']:
                        st.error(f"**Meses Caros:** {', '.join(patrones['meses_caros'])}")
                
                with col_pat2:
                    if patrones['meses_baratos']:
                        st.success(f"**Meses Baratos:** {', '.join(patrones['meses_baratos'])}")
                
                st.info(patrones['descripcion'])
        else:
            st.info("ℹ️ No hay suficientes datos para predicción con IA")

        # Sistema de notas
        st.markdown("### 📝 Agregar Nota")
        
        with st.form("nota_precio"):
            col_n1, col_n2 = st.columns([1, 2])
            
            with col_n1:
                fecha_nota = st.date_input("Fecha", date.today())
                tipo_evento = st.selectbox("Tipo", ["precio_alto", "precio_bajo", "normal", "atipico"])
            
            with col_n2:
                nota_texto = st.text_area("Comentario", placeholder="Ej: Helada causó escasez...")
            
            if st.form_submit_button("💾 Guardar"):
                if nota_texto:
                    if guardar_nota_precio(fecha_nota, producto_seleccionado, nota_texto, tipo_evento):
                        st.success("✅ Nota guardada")
                        st.rerun()
                else:
                    st.error("❌ Agrega un comentario")
        
        # Mostrar notas
        if not df_notas.empty:
            notas_producto = df_notas[df_notas['producto'] == producto_seleccionado].head(5)
            if not notas_producto.empty:
                st.markdown("#### 📚 Notas Recientes")
                for idx, nota in notas_producto.iterrows():
                    st.markdown(f"**{nota['fecha'].strftime('%d/%m/%Y')}** - {nota['nota']}")
                    st.caption(f"_{nota['tipo_evento']}_")


# ==================== FOOTER ====================

st.divider()
st.caption("Agrícola Montserrat - Sistema de Gestión v3.0 | FASE 1 Completa | Febrero 2026")
