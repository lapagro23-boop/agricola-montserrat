import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from supabase import create_client, Client
import io

# --- 1. CONFIGURACIÓN Y CONEXIÓN ---
st.set_page_config(page_title="Agrícola Montserrat 2026", layout="wide", page_icon="🍌")

# Manejo robusto de errores de conexión
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

# --- 2. FUNCIONES DE BASE DE DATOS (NUBE) ---
def cargar_datos():
    if not supabase: return pd.DataFrame()
    
    try:
        # Intentamos traer los datos. Si la tabla no existe o hay error, salta al except
        response = supabase.table("ventas_2026").select("*").execute()
        df = pd.DataFrame(response.data)
        
        if not df.empty:
            # Mapeo exacto de tus columnas
            mapa_cols = {
                'fecha': 'Fecha', 'producto': 'Producto', 'proveedor': 'Proveedor', 
                'cliente': 'Cliente', 'fec_doc_url': 'FEC_Doc', 'fev_doc_url': 'FEV_Doc', 
                'kg_compra': 'Kg_Compra', 'precio_compra': 'Precio_Compra', 'fletes': 'Fletes',
                'viaticos': 'Viaticos', 'otros_gastos': 'Otros_Gastos', 'kg_venta': 'Kg_Venta',
                'precio_venta': 'Precio_Venta', 'retenciones': 'Retenciones', 'descuentos': 'Descuentos',
                'utilidad': 'Utilidad', 'estado_pago': 'Estado_Pago', 'dias_credito': 'Dias_Credito'
            }
            # Solo renombramos si las columnas coinciden
            df = df.rename(columns=mapa_cols)
            # Aseguramos tipos de datos
            if 'Fecha' in df.columns:
                df['Fecha'] = pd.to_datetime(df['Fecha'])
            return df
            
    except Exception as e:
        # Si falla, mostramos el error pero no rompemos la app
        st.warning(f"Esperando datos... (Detalle: {e})")
    
    # Estructura vacía por defecto
    columnas = ["Fecha", "Producto", "Proveedor", "Cliente", "FEC_Doc", "FEV_Doc", 
               "Kg_Compra", "Precio_Compra", "Fletes", "Viaticos", "Otros_Gastos",
               "Kg_Venta", "Precio_Venta", "Retenciones", "Descuentos", 
               "Utilidad", "Estado_Pago", "Dias_Credito"]
    return pd.DataFrame(columns=columnas)

def subir_archivo(archivo, nombre_base):
    if archivo and supabase:
        try:
            nombre_archivo = f"{nombre_base}_{archivo.name}"
            archivo_bytes = archivo.getvalue()
            supabase.storage.from_(BUCKET_FACTURAS).upload(
                path=nombre_archivo, 
                file=archivo_bytes, 
                file_options={"content-type": archivo.type}
            )
            return supabase.storage.from_(BUCKET_FACTURAS).get_public_url(nombre_archivo)
        except Exception as e:
            st.warning(f"Nota: No se pudo subir imagen al bucket (¿Existe el bucket 'facturas'?). {e}")
            return ""
    return ""

def color_deuda(row):
    color = ''
    try:
        if row['Estado_Pago'] == 'Pagado':
            color = 'background-color: #d4edda; color: #155724;'
        elif row['Estado_Pago'] == 'Pendiente':
            vence = pd.to_datetime(row['Fecha']) + timedelta(days=int(row['Dias_Credito'] or 0))
            dias_rest = (vence - pd.Timestamp.now()).days
            if dias_rest < 0: color = 'background-color: #f8d7da; color: #721c24;'
            elif dias_rest <= 3: color = 'background-color: #fff3cd; color: #856404;'
    except: pass
    return [color] * len(row)

# --- INICIO DE LA APP ---
st.title("🌱 Agrícola Montserrat - Gestión Global")

df_completo = cargar_datos()

# BARRA LATERAL
st.sidebar.header("⚙️ Controles")
f_ini = st.sidebar.date_input("Inicio", date(2026, 1, 1))
f_fin = st.sidebar.date_input("Fin", date(2026, 12, 31))

if not df_completo.empty and 'Fecha' in df_completo.columns:
    mask = (df_completo['Fecha'].dt.date >= f_ini) & (df_completo['Fecha'].dt.date <= f_fin)
    df = df_completo.loc[mask].copy()
else:
    df = pd.DataFrame(columns=df_completo.columns)

tab1, tab2, tab3 = st.tabs(["📊 Balance de Peso", "🧮 Nueva Operación", "🚦 Cartera"])

# --- TAB 1: DASHBOARD ---
with tab1:
    if not df.empty:
        df['Diferencia_Kg'] = df['Kg_Venta'] - df['Kg_Compra']
        merma_solo = df[df['Diferencia_Kg'] < 0]['Diferencia_Kg'].sum()
        ganancia_solo = df[df['Diferencia_Kg'] > 0]['Diferencia_Kg'].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Utilidad", f"${df['Utilidad'].sum():,.0f}")
        c2.metric("📦 Kg Totales Vendidos", f"{df['Kg_Venta'].sum():,.1f}")
        c3.metric("⚖️ Merma (Pérdida)", f"{abs(merma_solo):,.1f} Kg", delta_color="inverse")
        c4.metric("📈 Ganancia de Peso", f"{ganancia_solo:,.1f} Kg", delta_color="normal")

        st.divider()
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.subheader("Balance de Kilos por Proveedor")
            dg = df.groupby('Proveedor')[['Diferencia_Kg']].sum().reset_index()
            fig = px.bar(dg, x='Proveedor', y='Diferencia_Kg', 
                         color='Diferencia_Kg', color_continuous_scale=['red', 'white', 'green'])
            st.plotly_chart(fig, use_container_width=True)
        with col_g2:
            st.subheader("Rentabilidad por Fruta")
            st.plotly_chart(px.pie(df, values='Utilidad', names='Producto', hole=0.4), use_container_width=True)
    else:
        st.info("👋 ¡Bienvenido! La base de datos está conectada pero vacía. Ve a la pestaña 'Nueva Operación' para registrar tu primer viaje.")

# --- TAB 2: CALCULADORA ---
with tab2:
    st.header("Cargar Nuevo Viaje")
    with st.form("registro_viaje", clear_on_submit=True):
        r1, r2, r3, r4 = st.columns(4)
        fecha_in = r1.date_input("Fecha", date.today())
        fruta = r2.selectbox("Fruta", ["Plátano", "Guayabo", "Papaya", "Otro"])
        prov = r3.text_input("Proveedor")
        cli = r4.text_input("Cliente")

        st.divider()
        col_c, col_v = st.columns(2)
        with col_c:
            st.subheader("1. Compra")
            kgc = st.number_input("Kg Comprados", min_value=0.0)
            pc = st.number_input("Precio Compra ($/Kg)", min_value=0.0)
            fl = st.number_input("Gastos Envío/Flete", min_value=0.0)
            fec_file = st.file_uploader("Subir Factura Compra")

        with col_v:
            st.subheader("2. Venta")
            kgv = st.number_input("Kg Vendidos", min_value=0.0)
            pv = st.number_input("Precio Venta ($/Kg)", min_value=0.0)
            desc = st.number_input("Deducciones/Ret", min_value=0.0)
            fev_file = st.file_uploader("Subir Factura Venta")

        # Balance en vivo
        if kgc > 0 and kgv > 0:
            dif = kgv - kgc
            if dif < 0: st.error(f"⚠️ MERMA: {abs(dif):.1f} Kg")
            elif dif > 0: st.success(f"🚀 GANANCIA: {dif:.1f} Kg")
        
        util_est = (kgv * pv) - (kgc * pc) - fl - desc
        st.metric("💰 Utilidad Estimada", f"${util_est:,.0f}")
        
        ce1, ce2 = st.columns(2)
        estado = ce1.selectbox("Estado", ["Pagado", "Pendiente"])
        dias = ce2.number_input("Días Crédito", 8)

        if st.form_submit_button("☁️ Guardar en Nube"):
            if prov and cli:
                with st.spinner("Subiendo datos a Supabase..."):
                    url_compra = subir_archivo(fec_file, f"compra_{prov}")
                    url_venta = subir_archivo(fev_file, f"venta_{cli}")

                    datos_nuevos = {
                        "fecha": str(fecha_in),
                        "producto": fruta, "proveedor": prov, "cliente": cli,
                        "fec_doc_url": url_compra, "fev_doc_url": url_venta,
                        "kg_compra": kgc, "precio_compra": pc, "fletes": fl, "viaticos": 0, "otros_gastos": 0,
                        "kg_venta": kgv, "precio_venta": pv, "retenciones": 0, "descuentos": desc,
                        "utilidad": util_est, "estado_pago": estado, "dias_credito": dias
                    }
                    
                    try:
                        supabase.table("ventas_2026").insert(datos_nuevos).execute()
                        st.success("¡Viaje guardado en la nube exitosamente!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error guardando en BD: {e}")
            else: st.error("Faltan datos obligatorios (Proveedor/Cliente).")

# --- TAB 3: CARTERA ---
with tab3:
    st.subheader("Registros Históricos (Nube)")
    if not df.empty:
        st.dataframe(
            df.style.apply(color_deuda, axis=1).format({"Utilidad": "${:,.0f}"}), 
            use_container_width=True,
            column_config={
                "FEC_Doc": st.column_config.LinkColumn("Fact. Compra"),
                "FEV_Doc": st.column_config.LinkColumn("Fact. Venta")
            }
        )
    else:
        st.write("Aún no hay registros en la base de datos.")


