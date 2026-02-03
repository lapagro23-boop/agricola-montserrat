import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta, datetime
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
        # Traemos también el 'id' para poder editar
        response = supabase.table("ventas_2026").select("*").order("fecha", desc=True).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            mapa_cols = {
                'id': 'ID', # Importante para editar
                'fecha': 'Fecha', 'producto': 'Producto', 'proveedor': 'Proveedor', 
                'cliente': 'Cliente', 'fec_doc_url': 'FEC_Doc', 'fev_doc_url': 'FEV_Doc', 
                'kg_compra': 'Kg_Compra', 'precio_compra': 'Precio_Compra', 'fletes': 'Fletes',
                'viaticos': 'Viaticos', 'otros_gastos': 'Otros_Gastos', 'kg_venta': 'Kg_Venta',
                'precio_venta': 'Precio_Venta', 'retenciones': 'Retenciones', 'descuentos': 'Descuentos',
                'utilidad': 'Utilidad', 'estado_pago': 'Estado_Pago', 'dias_credito': 'Dias_Credito'
            }
            # Renombramos solo las que existen
            df = df.rename(columns={k: v for k, v in mapa_cols.items() if k in df.columns})
            
            if 'Fecha' in df.columns:
                df['Fecha'] = pd.to_datetime(df['Fecha'])
            
            # Aseguramos que las URLs sean strings válidos
            cols_url = ['FEC_Doc', 'FEV_Doc']
            for col in cols_url:
                if col in df.columns:
                    df[col] = df[col].fillna("").astype(str)
                    # Si dice "None" o está vacío, lo dejamos vacío real
                    df.loc[df[col].isin(["None", "nan", ""]), col] = None
            
            return df
    except Exception as e:
        st.warning(f"Esperando datos... (Detalle: {e})")
    
    return pd.DataFrame()

def subir_archivo(archivo, nombre_base):
    if archivo and supabase:
        try:
            nombre_clean = "".join(c for c in archivo.name if c.isalnum() or c in "._- ")
            nombre_archivo = f"{nombre_base}_{datetime.now().strftime('%H%M%S')}_{nombre_clean}"
            archivo_bytes = archivo.getvalue()
            
            supabase.storage.from_(BUCKET_FACTURAS).upload(
                path=nombre_archivo, 
                file=archivo_bytes, 
                file_options={"content-type": archivo.type}
            )
            return supabase.storage.from_(BUCKET_FACTURAS).get_public_url(nombre_archivo)
        except Exception as e:
            st.warning(f"Error subiendo: {e}")
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
            elif dias_rest <= 3: color = 'background-color: #fff3cd; color: #856404;' 
    except: pass
    return [color] * len(row)

def obtener_opciones(df, col, defaults):
    existentes = df[col].unique().tolist() if not df.empty and col in df.columns else []
    lista_final = sorted(list(set(defaults + [x for x in existentes if x])))
    lista_final.append("➕ Nuevo...")
    return lista_final

# --- INICIO DE LA INTERFAZ ---
st.title("🌱 Agrícola Montserrat - Gestión Global")

df_completo = cargar_datos()

# 🔔 ALERTAS
if not df_completo.empty:
    hoy = date.today()
    # 1. Vencimientos
    if 'Estado_Pago' in df_completo.columns:
        pendientes = df_completo[df_completo['Estado_Pago'] == 'Pendiente'].copy()
        if not pendientes.empty:
            pendientes['Dias_Credito'] = pd.to_numeric(pendientes['Dias_Credito'], errors='coerce').fillna(0)
            pendientes['Vence'] = (pendientes['Fecha'] + pd.to_timedelta(pendientes['Dias_Credito'], unit='D')).dt.date
            pendientes['Dias_Restantes'] = (pendientes['Vence'] - hoy).apply(lambda x: x.days)
            
            urgentes = pendientes[pendientes['Dias_Restantes'] <= 3]
            if not urgentes.empty:
                st.error(f"🔔 ¡ATENCIÓN! {len(urgentes)} facturas críticas.")

    # 2. Resumen Mes
    if hoy.day <= 5:
        primer = hoy.replace(day=1)
        ultimo_anterior = primer - timedelta(days=1)
        inicio_anterior = ultimo_anterior.replace(day=1)
        
        mask = (df_completo['Fecha'].dt.date >= inicio_anterior) & (df_completo['Fecha'].dt.date <= ultimo_anterior)
        df_mes = df_completo.loc[mask]
        if not df_mes.empty:
            st.info(f"📅 Resumen {ultimo_anterior.strftime('%B')}: Ventas ${df_mes['Utilidad'].sum():,.0f} | {df_mes['Kg_Venta'].sum():,.0f} Kg")

# SIDEBAR
st.sidebar.header("⚙️ Filtros")
f_ini = st.sidebar.date_input("Inicio", date(2026, 1, 1))
f_fin = st.sidebar.date_input("Fin", date(2026, 12, 31))

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
        c1.metric("💰 Utilidad", f"${df['Utilidad'].sum():,.0f}")
        c2.metric("📦 Kg Movidos", f"{df['Kg_Venta'].sum():,.1f}")
        c3.metric("⚖️ Merma", f"{abs(merma):,.1f} Kg", delta_color="inverse")
        c4.metric("📈 Ganancia", f"{ganancia:,.1f} Kg")
        
        st.plotly_chart(px.bar(df, x='Proveedor', y='Utilidad', color='Producto', title="Utilidad por Proveedor"), use_container_width=True)
    else:
        st.info("No hay datos.")

# --- TAB 2: REGISTRO ---
with tab2:
    st.header("Registrar Viaje")
    with st.form("registro_viaje", clear_on_submit=True):
        r1, r2, r3, r4 = st.columns(4)
        fecha_in = r1.date_input("Fecha", date.today())
        
        # Desplegables
        l_prod = obtener_opciones(df_completo, 'Producto', ["Plátano", "Guayabo"])
        s_prod = r2.selectbox("Fruta", l_prod)
        t_prod = r2.text_input("Nombre Nueva Fruta") if s_prod == "➕ Nuevo..." else ""

        l_prov = obtener_opciones(df_completo, 'Proveedor', ["Omar", "Rancho"])
        s_prov = r3.selectbox("Proveedor", l_prov)
        t_prov = r3.text_input("Nombre Nuevo Prov.") if s_prov == "➕ Nuevo..." else ""

        l_cli = obtener_opciones(df_completo, 'Cliente', ["Calima", "Fogón", "HEFE"])
        s_cli = r4.selectbox("Cliente", l_cli)
        t_cli = r4.text_input("Nombre Nuevo Cli.") if s_cli == "➕ Nuevo..." else ""

        col_c, col_v = st.columns(2)
        with col_c:
            kgc = st.number_input("Kg Compra", min_value=0.0)
            pc = st.number_input("Precio Compra", min_value=0.0)
            fl = st.number_input("Fletes", min_value=0.0)
            fec_file = st.file_uploader("Factura Compra")
        with col_v:
            kgv = st.number_input("Kg Venta", min_value=0.0)
            pv = st.number_input("Precio Venta", min_value=0.0)
            desc = st.number_input("Deducciones", min_value=0.0)
            fev_file = st.file_uploader("Factura Venta")

        util_est = (kgv * pv) - (kgc * pc) - fl - desc
        st.metric("💰 Utilidad Estimada", f"${util_est:,.0f}")
        
        estado = st.selectbox("Estado", ["Pagado", "Pendiente"])
        dias = st.number_input("Días Crédito", 8)

        if st.form_submit_button("☁️ Guardar"):
            # Lógica de selección final
            fin_prod = t_prod if s_prod == "➕ Nuevo..." else s_prod
            fin_prov = t_prov if s_prov == "➕ Nuevo..." else s_prov
            fin_cli = t_cli if s_cli == "➕ Nuevo..." else s_cli

            if fin_prov and fin_cli:
                with st.spinner("Guardando..."):
                    uc = subir_archivo(fec_file, f"compra_{fin_prov}")
                    uv = subir_archivo(fev_file, f"venta_{fin_cli}")
                    
                    data = {
                        "fecha": str(fecha_in), "producto": fin_prod, "proveedor": fin_prov, "cliente": fin_cli,
                        "kg_compra": kgc, "precio_compra": pc, "fletes": fl, "viaticos": 0, "otros_gastos": 0,
                        "kg_venta": kgv, "precio_venta": pv, "retenciones": 0, "descuentos": desc,
                        "utilidad": util_est, "estado_pago": estado, "dias_credito": dias,
                        "fec_doc_url": uc if uc else "", "fev_doc_url": uv if uv else ""
                    }
                    supabase.table("ventas_2026").insert(data).execute()
                    st.success("Guardado!")
                    st.rerun()
            else:
                st.error("Faltan nombres obligatorios.")

# --- TAB 3: CARTERA Y EDICIÓN ---
with tab3:
    st.subheader("Historial (Selecciona para Editar)")
    if not df.empty:
        # 1. Tabla con selección
        event = st.dataframe(
            df.style.apply(color_deuda, axis=1).format({"Utilidad": "${:,.0f}"}),
            use_container_width=True,
            column_config={
                "FEC_Doc": st.column_config.LinkColumn("F. Compra", display_text="📎 Ver"),
                "FEV_Doc": st.column_config.LinkColumn("F. Venta", display_text="📎 Ver"),
                "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            },
            selection_mode="single-row",
            on_select="rerun",
            hide_index=True
        )

        # 2. Formulario de Edición
        if event.selection.rows:
            idx = event.selection.rows[0]
            row_data = df.iloc[idx]
            id_row = row_data['ID']

            st.divider()
            st.markdown(f"### ✏️ Editando Viaje de: **{row_data['Proveedor']}** -> **{row_data['Cliente']}** ({row_data['Fecha'].date()})")
            
            with st.form("form_edicion"):
                c1, c2, c3 = st.columns(3)
                e_kgv = c1.number_input("Kg Venta", value=float(row_data['Kg_Venta']))
                e_pv = c2.number_input("Precio Venta", value=float(row_data['Precio_Venta']))
                e_est = c3.selectbox("Estado", ["Pagado", "Pendiente"], index=0 if row_data['Estado_Pago'] == "Pagado" else 1)
                
                # Archivos (Opcional reemplazar)
                st.caption("Subir nuevos archivos solo si deseas reemplazar los actuales:")
                e_file_c = st.file_uploader("Reemplazar Fac. Compra")
                e_file_v = st.file_uploader("Reemplazar Fac. Venta")

                if st.form_submit_button("💾 Actualizar Registro"):
                    updates = {
                        "kg_venta": e_kgv,
                        "precio_venta": e_pv,
                        "estado_pago": e_est,
                        # Recalcular utilidad automáticamente al editar
                        "utilidad": (e_kgv * e_pv) - (row_data['Kg_Compra'] * row_data['Precio_Compra']) - row_data['Fletes'] - row_data['Descuentos']
                    }
                    
                    if e_file_c:
                        updates["fec_doc_url"] = subir_archivo(e_file_c, f"edit_compra_{row_data['Proveedor']}")
                    if e_file_v:
                        updates["fev_doc_url"] = subir_archivo(e_file_v, f"edit_venta_{row_data['Cliente']}")
                    
                    supabase.table("ventas_2026").update(updates).eq("id", int(id_row)).execute()
                    st.success("Registro actualizado.")
                    st.rerun()
    else:
        st.write("No hay datos.")




