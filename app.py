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
            
            # --- ARREGLO DEFINITIVO DE ARCHIVOS ---
            # Si la celda está vacía o es 'None' (texto), la volvemos None (objeto)
            # Esto es vital para que Streamlit detecte los links
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
            # Limpieza de nombre más estricta para evitar errores de URL
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
            elif dias_rest <= 3: color = 'background-color: #fff3cd; color: #856404;' 
    except: pass
    return [color] * len(row)

def obtener_opciones(df, col, defaults):
    existentes = df[col].unique().tolist() if not df.empty and col in df.columns else []
    lista_final = sorted(list(set(defaults + [x for x in existentes if x])))
    return lista_final

# --- INICIO DE LA INTERFAZ ---
st.title("🌱 Agrícola Montserrat - Gestión Global")

df_completo = cargar_datos()

# SIDEBAR & FILTROS
st.sidebar.header("⚙️ Configuración")
ver_resumen = st.sidebar.checkbox("👁️ Ver Resumen Mensual", value=(date.today().day <= 5))
st.sidebar.divider()
f_ini = st.sidebar.date_input("Inicio", date(2026, 1, 1))
f_fin = st.sidebar.date_input("Fin", date(2026, 12, 31))

# 🔔 ALERTAS Y RESUMEN (ZONA SUPERIOR)
if not df_completo.empty:
    hoy = date.today()
    
    # 1. Alerta de Cobros (Siempre visible si hay urgencias)
    if 'Estado_Pago' in df_completo.columns:
        pendientes = df_completo[df_completo['Estado_Pago'] == 'Pendiente'].copy()
        if not pendientes.empty:
            pendientes['Dias_Credito'] = pd.to_numeric(pendientes['Dias_Credito'], errors='coerce').fillna(0)
            pendientes['Vence'] = (pendientes['Fecha'] + pd.to_timedelta(pendientes['Dias_Credito'], unit='D')).dt.date
            pendientes['Dias_Restantes'] = (pendientes['Vence'] - hoy).apply(lambda x: x.days)
            
            urgentes = pendientes[pendientes['Dias_Restantes'] <= 3]
            if not urgentes.empty:
                st.error(f"🔔 ¡URGENTE! Tienes {len(urgentes)} facturas críticas por cobrar.")

    # 2. Resumen Mensual (Restaurado y Mejorado)
    if ver_resumen:
        primer = hoy.replace(day=1)
        ultimo_anterior = primer - timedelta(days=1)
        inicio_anterior = ultimo_anterior.replace(day=1)
        
        # Filtramos datos del mes anterior
        mask_mes = (df_completo['Fecha'].dt.date >= inicio_anterior) & (df_completo['Fecha'].dt.date <= ultimo_anterior)
        df_mes = df_completo.loc[mask_mes]
        
        with st.expander(f"📅 Resumen del Mes Anterior ({ultimo_anterior.strftime('%B %Y')})", expanded=True):
            if not df_mes.empty:
                c_res1, c_res2, c_res3, c_res4 = st.columns(4)
                utilidad_mes = df_mes['Utilidad'].sum()
                kg_mes = df_mes['Kg_Venta'].sum()
                c_res1.metric("💵 Utilidad Total", f"${utilidad_mes:,.0f}")
                c_res2.metric("📦 Kg Vendidos", f"{kg_mes:,.1f}")
                
                # Rentabilidad simple: Utilidad / Venta Total
                venta_bruta = (df_mes['Kg_Venta'] * df_mes['Precio_Venta']).sum()
                rentabilidad = (utilidad_mes / venta_bruta * 100) if venta_bruta > 0 else 0
                c_res3.metric("📊 Rentabilidad", f"{rentabilidad:.1f}%")
                c_res4.caption("Este resumen se muestra automáticamente los primeros 5 días del mes, o puedes activarlo en el menú lateral.")
            else:
                st.info("No hubo movimientos registrados el mes anterior.")

# FILTRO DE FECHAS PRINCIPAL
if not df_completo.empty:
    mask = (df_completo['Fecha'].dt.date >= f_ini) & (df_completo['Fecha'].dt.date <= f_fin)
    df = df_completo.loc[mask].copy()
else:
    df = pd.DataFrame(columns=df_completo.columns)

# PESTAÑAS PRINCIPALES
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
        st.info("No hay datos en el rango de fechas seleccionado.")

# --- TAB 2: REGISTRO ---
with tab2:
    st.header("Registrar Viaje")
    with st.form("registro_viaje", clear_on_submit=True):
        r1, r2, r3, r4 = st.columns(4)
        fecha_in = r1.date_input("Fecha", date.today())
        
        # Selección Simplificada
        l_prod = obtener_opciones(df_completo, 'Producto', ["Plátano", "Guayabo"])
        s_prod = r2.selectbox("Fruta", l_prod)
        n_prod = r2.text_input("¿Otra fruta?", placeholder="Escribe si no está en lista")
        
        l_prov = obtener_opciones(df_completo, 'Proveedor', ["Omar", "Rancho"])
        s_prov = r3.selectbox("Proveedor", l_prov)
        n_prov = r3.text_input("¿Otro proveedor?", placeholder="Escribe si no está en lista")

        l_cli = obtener_opciones(df_completo, 'Cliente', ["Calima", "Fogón", "HEFE"])
        s_cli = r4.selectbox("Cliente", l_cli)
        n_cli = r4.text_input("¿Otro cliente?", placeholder="Escribe si no está en lista")

        col_c, col_v = st.columns(2)
        with col_c:
            st.subheader("Compra")
            kgc = st.number_input("Kg Compra", min_value=0.0)
            pc = st.number_input("Precio Compra", min_value=0.0)
            fl = st.number_input("Fletes", min_value=0.0)
            fec_file = st.file_uploader("Factura Compra (PDF/Foto)")
        with col_v:
            st.subheader("Venta")
            kgv = st.number_input("Kg Venta", min_value=0.0)
            pv = st.number_input("Precio Venta", min_value=0.0)
            desc = st.number_input("Deducciones", min_value=0.0)
            fev_file = st.file_uploader("Factura Venta (PDF/Foto)")

        util_est = (kgv * pv) - (kgc * pc) - fl - desc
        st.metric("💰 Utilidad Estimada", f"${util_est:,.0f}")
        
        estado = st.selectbox("Estado", ["Pagado", "Pendiente"])
        dias = st.number_input("Días Crédito", 8)

        if st.form_submit_button("☁️ Guardar"):
            fin_prod = n_prod if n_prod else s_prod
            fin_prov = n_prov if n_prov else s_prov
            fin_cli = n_cli if n_cli else s_cli

            if fin_prov and fin_cli:
                with st.spinner("Subiendo archivos y guardando..."):
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
                    st.success("✅ ¡Registro guardado con éxito!")
                    st.rerun()
            else:
                st.error("❌ Faltan datos obligatorios (Proveedor o Cliente).")

# --- TAB 3: CARTERA Y EDICIÓN ---
with tab3:
    st.subheader("Historial (Selecciona fila para Editar)")
    if not df.empty:
        # Configuración de Columnas para Links
        column_cfg = {
            "FEC_Doc": st.column_config.LinkColumn("F. Compra", display_text="📎 Ver Doc"),
            "FEV_Doc": st.column_config.LinkColumn("F. Venta", display_text="📎 Ver Doc"),
            "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "Utilidad": st.column_config.NumberColumn("Utilidad", format="$%d")
        }

        # Tabla Interactiva
        event = st.dataframe(
            df.style.apply(color_deuda, axis=1),
            use_container_width=True,
            column_config=column_cfg,
            selection_mode="single-row",
            on_select="rerun",
            hide_index=True
        )

        # Formulario de Edición
        if event.selection.rows:
            idx = event.selection.rows[0]
            row_data = df.iloc[idx]
            id_row = row_data['ID']

            st.divider()
            st.markdown(f"### ✏️ Editando: **{row_data['Cliente']}** - {row_data['Fecha'].strftime('%d/%m')}")
            
            with st.form("form_edicion"):
                c1, c2, c3, c4 = st.columns(4)
                e_kgc = c1.number_input("Kg Compra", value=float(row_data['Kg_Compra']))
                e_pc = c2.number_input("Precio Compra", value=float(row_data['Precio_Compra']))
                e_kgv = c3.number_input("Kg Venta", value=float(row_data['Kg_Venta']))
                e_pv = c4.number_input("Precio Venta", value=float(row_data['Precio_Venta']))

                c5, c6 = st.columns(2)
                e_est = c5.selectbox("Estado", ["Pagado", "Pendiente"], index=0 if row_data['Estado_Pago'] == "Pagado" else 1)
                
                st.markdown("---")
                st.caption("📂 Reemplazar archivos (Dejar vacío si no quieres cambiarlos)")
                col_fa, col_fb = st.columns(2)
                e_file_c = col_fa.file_uploader("Nueva Fac. Compra")
                e_file_v = col_fb.file_uploader("Nueva Fac. Venta")

                if st.form_submit_button("💾 Guardar Cambios"):
                    # Recálculo
                    gastos = row_data['Fletes'] + row_data['Descuentos'] + row_data['Viaticos'] + row_data['Otros_Gastos']
                    new_util = (e_kgv * e_pv) - (e_kgc * e_pc) - gastos

                    updates = {
                        "kg_compra": e_kgc, "precio_compra": e_pc,
                        "kg_venta": e_kgv, "precio_venta": e_pv,
                        "estado_pago": e_est,
                        "utilidad": new_util
                    }
                    
                    if e_file_c:
                        updates["fec_doc_url"] = subir_archivo(e_file_c, f"edit_compra_{row_data['Proveedor']}")
                    if e_file_v:
                        updates["fev_doc_url"] = subir_archivo(e_file_v, f"edit_venta_{row_data['Cliente']}")
                    
                    supabase.table("ventas_2026").update(updates).eq("id", int(id_row)).execute()
                    st.success("✅ Registro actualizado.")
                    st.rerun()
            
            if st.button("🗑️ Eliminar este registro", type="primary"):
                supabase.table("ventas_2026").delete().eq("id", int(id_row)).execute()
                st.warning("Registro eliminado.")
                st.rerun()
    else:
        st.write("No hay registros disponibles.")







