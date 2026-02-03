import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from supabase import create_client, Client
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
def cargar_datos():
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table("ventas_2026").select("*").execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            mapa_cols = {
                'fecha': 'Fecha', 'producto': 'Producto', 'proveedor': 'Proveedor', 
                'cliente': 'Cliente', 'fec_doc_url': 'FEC_Doc', 'fev_doc_url': 'FEV_Doc', 
                'kg_compra': 'Kg_Compra', 'precio_compra': 'Precio_Compra', 'fletes': 'Fletes',
                'viaticos': 'Viaticos', 'otros_gastos': 'Otros_Gastos', 'kg_venta': 'Kg_Venta',
                'precio_venta': 'Precio_Venta', 'retenciones': 'Retenciones', 'descuentos': 'Descuentos',
                'utilidad': 'Utilidad', 'estado_pago': 'Estado_Pago', 'dias_credito': 'Dias_Credito'
            }
            df = df.rename(columns=mapa_cols)
            if 'Fecha' in df.columns:
                df['Fecha'] = pd.to_datetime(df['Fecha'])
            
            # Limpiamos URLs vacías
            cols_url = ['FEC_Doc', 'FEV_Doc']
            for col in cols_url:
                if col in df.columns:
                    df[col] = df[col].replace('', None).replace('None', None)
            
            return df
    except Exception as e:
        st.warning(f"Esperando datos... (Detalle: {e})")
    
    return pd.DataFrame(columns=["Fecha", "Producto", "Proveedor", "Cliente", "FEC_Doc", "FEV_Doc", 
               "Kg_Compra", "Precio_Compra", "Fletes", "Viaticos", "Otros_Gastos",
               "Kg_Venta", "Precio_Venta", "Retenciones", "Descuentos", 
               "Utilidad", "Estado_Pago", "Dias_Credito"])

def subir_archivo(archivo, nombre_base):
    if archivo and supabase:
        try:
            nombre_clean = "".join(c for c in archivo.name if c.isalnum() or c in "._- ")
            nombre_archivo = f"{nombre_base}_{date.today()}_{nombre_clean}"
            archivo_bytes = archivo.getvalue()
            
            supabase.storage.from_(BUCKET_FACTURAS).upload(
                path=nombre_archivo, 
                file=archivo_bytes, 
                file_options={"content-type": archivo.type}
            )
            return supabase.storage.from_(BUCKET_FACTURAS).get_public_url(nombre_archivo)
        except Exception as e:
            st.warning(f"Error subiendo imagen: {e}")
            return None
    return None

def color_deuda(row):
    color = ''
    try:
        if row['Estado_Pago'] == 'Pagado':
            color = 'background-color: #d4edda; color: #155724;'
        elif row['Estado_Pago'] == 'Pendiente':
            # Cálculo seguro de fechas para el color
            try:
                dias = int(row['Dias_Credito']) if pd.notnull(row['Dias_Credito']) else 0
                vence = row['Fecha'] + timedelta(days=dias)
                dias_rest = (vence.date() - date.today()).days
                
                if dias_rest < 0: color = 'background-color: #f8d7da; color: #721c24;' 
                elif dias_rest <= 3: color = 'background-color: #fff3cd; color: #856404;' 
            except:
                pass
    except: pass
    return [color] * len(row)

# --- INICIO DE LA INTERFAZ ---
st.title("🌱 Agrícola Montserrat - Gestión Global")

df_completo = cargar_datos()

# 🔔 ZONA DE ALERTAS
if not df_completo.empty:
    hoy = date.today()
    
    # 1. Alerta de Vencimientos
    pendientes = df_completo[df_completo['Estado_Pago'] == 'Pendiente'].copy()
    if not pendientes.empty:
        # --- CORRECCIÓN AQUÍ: Suma de fechas robusta ---
        # Aseguramos que Dias_Credito sea número y llenamos vacíos con 0
        pendientes['Dias_Credito'] = pd.to_numeric(pendientes['Dias_Credito'], errors='coerce').fillna(0)
        
        # Sumamos Fecha (Timestamp) + Timedelta (Días) y luego sacamos la fecha (.dt.date)
        pendientes['Vence'] = (pendientes['Fecha'] + pd.to_timedelta(pendientes['Dias_Credito'], unit='D')).dt.date
        
        # Calculamos diferencia contra hoy
        pendientes['Dias_Restantes'] = (pendientes['Vence'] - hoy).apply(lambda x: x.days)
        
        urgentes = pendientes[pendientes['Dias_Restantes'] <= 3]
        
        if not urgentes.empty:
            st.error(f"🔔 ¡ATENCIÓN! Tienes {len(urgentes)} facturas por cobrar críticas.")
            # Mostramos tabla simplificada
            df_urgentes_show = urgentes[['Cliente', 'Utilidad', 'Dias_Restantes', 'Vence']].sort_values('Dias_Restantes')
            st.dataframe(df_urgentes_show.style.format({"Utilidad": "${:,.0f}"}), use_container_width=True)

    # 2. Resumen Mensual (Primeros 5 días del mes)
    if hoy.day <= 5:
        primer_dia_mes_actual = hoy.replace(day=1)
        ultimo_dia_mes_anterior = primer_dia_mes_actual - timedelta(days=1)
        mes_anterior_inicio = ultimo_dia_mes_anterior.replace(day=1)
        
        mask_mes = (df_completo['Fecha'].dt.date >= mes_anterior_inicio) & (df_completo['Fecha'].dt.date <= ultimo_dia_mes_anterior)
        df_mes = df_completo.loc[mask_mes]
        
        if not df_mes.empty:
            nombre_mes = ultimo_dia_mes_anterior.strftime("%B")
            st.info(f"📅 **Resumen del Mes Anterior ({nombre_mes})**")
            m1, m2, m3 = st.columns(3)
            m1.metric("Ventas Totales", f"${df_mes['Utilidad'].sum():,.0f}")
            m2.metric("Kg Vendidos", f"{df_mes['Kg_Venta'].sum():,.1f}")
            rentabilidad = (df_mes['Utilidad'].sum() / (df_mes['Kg_Venta'].sum() * df_mes['Precio_Venta'].mean())) * 100 if df_mes['Kg_Venta'].sum() > 0 else 0
            m3.metric("Rentabilidad Aprox", f"{rentabilidad:.1f}%")

# BARRA LATERAL
st.sidebar.header("⚙️ Filtros")
f_ini = st.sidebar.date_input("Inicio", date(2026, 1, 1))
f_fin = st.sidebar.date_input("Fin", date(2026, 12, 31))

if not df_completo.empty:
    mask = (df_completo['Fecha'].dt.date >= f_ini) & (df_completo['Fecha'].dt.date <= f_fin)
    df = df_completo.loc[mask].copy()
else:
    df = pd.DataFrame(columns=df_completo.columns)

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🧮 Nueva Operación", "🚦 Cartera & Archivos"])

# --- TAB 1: DASHBOARD ---
with tab1:
    if not df.empty:
        df['Diferencia_Kg'] = df['Kg_Venta'] - df['Kg_Compra']
        merma_solo = df[df['Diferencia_Kg'] < 0]['Diferencia_Kg'].sum()
        ganancia_solo = df[df['Diferencia_Kg'] > 0]['Diferencia_Kg'].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Utilidad Neta", f"${df['Utilidad'].sum():,.0f}")
        c2.metric("📦 Kg Movidos", f"{df['Kg_Venta'].sum():,.1f}")
        c3.metric("⚖️ Merma", f"{abs(merma_solo):,.1f} Kg", delta_color="inverse")
        c4.metric("📈 Ganancia Peso", f"{ganancia_solo:,.1f} Kg")

        st.divider()
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            dg = df.groupby('Proveedor')[['Diferencia_Kg']].sum().reset_index()
            fig = px.bar(dg, x='Proveedor', y='Diferencia_Kg', title="Balance de Kilos por Proveedor",
                         color='Diferencia_Kg', color_continuous_scale=['red', 'gray', 'green'])
            st.plotly_chart(fig, use_container_width=True)
        with col_g2:
            st.plotly_chart(px.pie(df, values='Utilidad', names='Producto', title="Utilidad por Fruta", hole=0.4), use_container_width=True)
    else:
        st.info("Sin datos en el rango seleccionado.")

# --- TAB 2: CALCULADORA ---
with tab2:
    st.header("Registrar Viaje")
    with st.form("registro_viaje", clear_on_submit=True):
        r1, r2, r3, r4 = st.columns(4)
        fecha_in = r1.date_input("Fecha", date.today())
        fruta = r2.selectbox("Fruta", ["Plátano", "Guayabo", "Papaya", "Otro"])
        prov = r3.text_input("Proveedor")
        cli = r4.text_input("Cliente")

        st.divider()
        col_c, col_v = st.columns(2)
        with col_c:
            st.subheader("Compra")
            kgc = st.number_input("Kg Compra", min_value=0.0)
            pc = st.number_input("Precio Compra", min_value=0.0)
            fl = st.number_input("Fletes/Gastos", min_value=0.0)
            fec_file = st.file_uploader("Factura Compra (Foto/PDF)")

        with col_v:
            st.subheader("Venta")
            kgv = st.number_input("Kg Venta", min_value=0.0)
            pv = st.number_input("Precio Venta", min_value=0.0)
            desc = st.number_input("Deducciones", min_value=0.0)
            fev_file = st.file_uploader("Factura Venta (Foto/PDF)")

        util_est = (kgv * pv) - (kgc * pc) - fl - desc
        st.metric("💰 Utilidad Estimada", f"${util_est:,.0f}")
        
        ce1, ce2 = st.columns(2)
        estado = ce1.selectbox("Estado Pago", ["Pagado", "Pendiente"])
        dias = ce2.number_input("Días Crédito", 8)

        if st.form_submit_button("☁️ Guardar Viaje"):
            if prov and cli:
                with st.spinner("Subiendo archivos y datos..."):
                    url_compra = subir_archivo(fec_file, f"compra_{prov}")
                    url_venta = subir_archivo(fev_file, f"venta_{cli}")

                    datos_nuevos = {
                        "fecha": str(fecha_in),
                        "producto": fruta, "proveedor": prov, "cliente": cli,
                        "fec_doc_url": url_compra if url_compra else "",
                        "fev_doc_url": url_venta if url_venta else "",
                        "kg_compra": kgc, "precio_compra": pc, "fletes": fl, "viaticos": 0, "otros_gastos": 0,
                        "kg_venta": kgv, "precio_venta": pv, "retenciones": 0, "descuentos": desc,
                        "utilidad": util_est, "estado_pago": estado, "dias_credito": dias
                    }
                    
                    try:
                        supabase.table("ventas_2026").insert(datos_nuevos).execute()
                        st.success("✅ ¡Registro guardado exitosamente!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
            else: st.error("Falta Proveedor o Cliente.")

# --- TAB 3: CARTERA ---
with tab3:
    st.subheader("Historial de Operaciones")
    if not df.empty:
        st.dataframe(
            df.style.apply(color_deuda, axis=1).format({"Utilidad": "${:,.0f}", "Kg_Venta": "{:,.1f}"}), 
            use_container_width=True,
            column_config={
                "FEC_Doc": st.column_config.LinkColumn("📄 F. Compra", display_text="Ver Factura"),
                "FEV_Doc": st.column_config.LinkColumn("📄 F. Venta", display_text="Ver Factura"),
                "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            },
            hide_index=True
        )
    else:
        st.write("No hay registros disponibles.")



