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
                'utilidad': 'Utilidad', 'estado_pago': 'Estado_Pago', 'dias_credito': 'Dias_Credito',
                'precio_plaza': 'Precio_Plaza' # NUEVO CAMPO
            }
            df = df.rename(columns={k: v for k, v in mapa_cols.items() if k in df.columns})
            
            if 'Fecha' in df.columns:
                df['Fecha'] = pd.to_datetime(df['Fecha'])
            
            # Limpieza de URLs
            cols_url = ['FEC_Doc', 'FEV_Doc']
            for col in cols_url:
                if col in df.columns:
                    df[col] = df[col].replace({'': None, 'None': None, 'nan': None})
            
            # Asegurar que Precio_Plaza exista y sea numérico
            if 'Precio_Plaza' not in df.columns:
                df['Precio_Plaza'] = 0.0
            else:
                df['Precio_Plaza'] = pd.to_numeric(df['Precio_Plaza']).fillna(0.0)

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
    return sorted(list(set(defaults + [x for x in existentes if x])))

@st.cache_data
def convertir_df_a_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# --- INICIO DE LA INTERFAZ ---
st.title("🌱 Agrícola Montserrat - Gestión Global")

# SIDEBAR
st.sidebar.header("⚙️ Configuración")
if st.sidebar.button("🔄 Actualizar Datos"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.divider()
f_ini = st.sidebar.date_input("Inicio", date(2026, 1, 1))
f_fin = st.sidebar.date_input("Fin", date(2026, 12, 31))

df_completo = cargar_datos()

# DESCARGA CSV
if not df_completo.empty:
    st.sidebar.divider()
    st.sidebar.subheader("📂 Contabilidad")
    csv = convertir_df_a_csv(df_completo)
    st.sidebar.download_button(
        label="📥 Descargar Reporte (CSV)",
        data=csv,
        file_name=f"Reporte_Agricola_{date.today()}.csv",
        mime="text/csv",
    )

ver_resumen = st.sidebar.checkbox("👁️ Ver Resumen Mensual", value=(date.today().day <= 5))

# ALERTAS
if not df_completo.empty:
    hoy = date.today()
    if 'Estado_Pago' in df_completo.columns:
        pendientes = df_completo[df_completo['Estado_Pago'] == 'Pendiente'].copy()
        if not pendientes.empty:
            pendientes['Dias_Credito'] = pd.to_numeric(pendientes['Dias_Credito'], errors='coerce').fillna(0)
            pendientes['Vence'] = (pendientes['Fecha'] + pd.to_timedelta(pendientes['Dias_Credito'], unit='D')).dt.date
            pendientes['Dias_Restantes'] = (pendientes['Vence'] - hoy).apply(lambda x: x.days)
            urgentes = pendientes[pendientes['Dias_Restantes'] <= 3]
            if not urgentes.empty:
                st.error(f"🔔 ¡ATENCIÓN! Tienes {len(urgentes)} facturas críticas por cobrar.")

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

# FILTRO FECHAS
if not df_completo.empty:
    mask = (df_completo['Fecha'].dt.date >= f_ini) & (df_completo['Fecha'].dt.date <= f_fin)
    df = df_completo.loc[mask].copy()
else:
    df = pd.DataFrame(columns=df_completo.columns)

# PESTAÑAS
tab1, tab_ana, tab2, tab3 = st.tabs(["📊 Dashboard", "📈 Analítica Avanzada", "🧮 Nueva Operación", "🚦 Cartera & Edición"])

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

# --- TAB NUEVA: ANALÍTICA (Con Plaza) ---
with tab_ana:
    st.header("🧠 Inteligencia de Mercado")
    if not df.empty:
        # Filtrar solo los que tienen dato de plaza válido
        df_plaza = df[df['Precio_Plaza'] > 0].copy()
        
        # 1. Gráfica Comparativa (Compra vs Plaza)
        col_graf, col_info = st.columns([2, 1])
        
        with col_graf:
            st.subheader("📉 Nosotros (Azul) vs. La Plaza (Rojo)")
            if not df_plaza.empty:
                df_line = df_plaza.sort_values("Fecha")
                fig_line = px.line(df_line, x='Fecha', y=['Precio_Compra', 'Precio_Plaza'], 
                                   markers=True, title="Histórico de Precios")
                # Personalizamos colores
                new_names = {'Precio_Compra': 'Mi Compra (Campesino)', 'Precio_Plaza': 'Precio Mercado (Plaza)'}
                fig_line.for_each_trace(lambda t: t.update(name = new_names[t.name],
                                                         legendgroup = new_names[t.name],
                                                         hovertemplate = t.hovertemplate.replace(t.name, new_names[t.name])
                                                         ))
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.info("Aún no tienes registros con 'Precio Plaza' para mostrar la comparación.")

        with col_info:
            st.subheader("💡 Informe de Competitividad")
            if not df_plaza.empty:
                prom_compra = df_plaza['Precio_Compra'].mean()
                prom_plaza = df_plaza['Precio_Plaza'].mean()
                diff = prom_plaza - prom_compra
                ahorro_perc = (diff / prom_plaza * 100) if prom_plaza > 0 else 0
                
                st.metric("Precio Promedio Plaza", f"${prom_plaza:,.0f}")
                st.metric("Mi Precio Promedio", f"${prom_compra:,.0f}")
                
                if diff > 0:
                    st.success(f"✅ ¡Excelente! Estás comprando ${diff:,.0f} más barato que la plaza ({ahorro_perc:.1f}% de ventaja).")
                elif diff < 0:
                    st.error(f"⚠️ Cuidado: Estás pagando ${abs(diff):,.0f} más caro que el precio de mercado.")
                else:
                    st.warning("Estás comprando al mismo precio que la plaza.")
            else:
                st.write("Registra nuevos viajes con el dato de 'Precio Plaza' para ver tu ventaja competitiva aquí.")

        st.divider()
        # Otros rankings
        c_a, c_b = st.columns(2)
        with c_a:
            st.markdown("**🏆 Top Clientes (Utilidad)**")
            df_cli = df.groupby('Cliente')[['Utilidad']].sum().reset_index().sort_values('Utilidad', ascending=True)
            st.plotly_chart(px.bar(df_cli, x='Utilidad', y='Cliente', orientation='h', color='Utilidad'), use_container_width=True)
        with c_b:
            st.markdown("**⚖️ Calidad Prov. (% Merma)**")
            df_prov = df.groupby('Proveedor')[['Kg_Compra', 'Kg_Venta']].sum().reset_index()
            df_prov['Diferencia'] = df_prov['Kg_Compra'] - df_prov['Kg_Venta']
            df_prov['% Merma'] = (df_prov['Diferencia'] / df_prov['Kg_Compra']) * 100
            st.plotly_chart(px.bar(df_prov, x='Proveedor', y='% Merma', color='% Merma', color_continuous_scale=["green", "red"]), use_container_width=True)
            
    else:
        st.info("Necesitas datos.")

# --- TAB 2: REGISTRO (Con Campo Plaza) ---
with tab2:
    st.header("Registrar Viaje")
    with st.form("registro_viaje", clear_on_submit=True):
        r1, r2, r3, r4 = st.columns(4)
        fecha_in = r1.date_input("Fecha", date.today())
        
        l_prod = obtener_opciones(df_completo, 'Producto', ["Plátano", "Guayabo"])
        s_prod = r2.selectbox("Fruta", l_prod)
        n_prod = r2.text_input("¿Otra fruta?", placeholder="Escribe si no está")
        
        l_prov = obtener_opciones(df_completo, 'Proveedor', ["Omar", "Rancho"])
        s_prov = r3.selectbox("Proveedor", l_prov)
        n_prov = r3.text_input("¿Otro proveedor?", placeholder="Escribe si no está")

        l_cli = obtener_opciones(df_completo, 'Cliente', ["Calima", "Fogón", "HEFE"])
        s_cli = r4.selectbox("Cliente", l_cli)
        n_cli = r4.text_input("¿Otro cliente?", placeholder="Escribe si no está")

        col_c, col_v = st.columns(2)
        with col_c:
            kgc = st.number_input("Kg Compra", min_value=0.0)
            pc = st.number_input("Precio Compra (Campesino)", min_value=0.0, format="%.0f")
            # NUEVO CAMPO: PRECIO PLAZA
            pplaza = st.number_input("Precio en Plaza (Referencia)", min_value=0.0, format="%.0f", help="¿A cómo está en el mercado hoy?")
            fl = st.number_input("Fletes", min_value=0.0)
            fec_file = st.file_uploader("Factura Compra (PDF/Foto)")

        with col_v:
            kgv = st.number_input("Kg Venta", min_value=0.0)
            pv = st.number_input("Precio Venta", min_value=0.0, format="%.0f")
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
                with st.spinner("Guardando..."):
                    uc = subir_archivo(fec_file, f"compra_{fin_prov}")
                    uv = subir_archivo(fev_file, f"venta_{fin_cli}")
                    
                    data = {
                        "fecha": str(fecha_in), "producto": fin_prod, "proveedor": fin_prov, "cliente": fin_cli,
                        "kg_compra": kgc, "precio_compra": pc, "fletes": fl, "viaticos": 0, "otros_gastos": 0,
                        "kg_venta": kgv, "precio_venta": pv, "retenciones": 0, "descuentos": desc,
                        "utilidad": util_est, "estado_pago": estado, "dias_credito": dias,
                        "precio_plaza": pplaza, # Guardamos el nuevo dato
                        "fec_doc_url": uc if uc else "", "fev_doc_url": uv if uv else ""
                    }
                    supabase.table("ventas_2026").insert(data).execute()
                    st.cache_data.clear()
                    st.success("✅ ¡Guardado!")
                    st.rerun()
            else:
                st.error("Faltan datos obligatorios.")

# --- TAB 3: CARTERA Y EDICIÓN ---
with tab3:
    st.subheader("Historial (Selecciona fila para Editar)")
    if not df.empty:
        column_cfg = {
            "FEC_Doc": st.column_config.LinkColumn("F. Compra", display_text="📎 Doc"),
            "FEV_Doc": st.column_config.LinkColumn("F. Venta", display_text="📎 Doc"),
            "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "Utilidad": st.column_config.NumberColumn("Utilidad", format="$%d"),
            "Precio_Plaza": st.column_config.NumberColumn("Ref. Plaza", format="$%d")
        }

        event = st.dataframe(
            df.style.apply(color_deuda, axis=1),
            use_container_width=True,
            column_config=column_cfg,
            selection_mode="single-row",
            on_select="rerun",
            hide_index=True
        )

        if event.selection.rows:
            idx = event.selection.rows[0]
            row_data = df.iloc[idx]
            id_row = row_data['ID']

            st.divider()
            st.markdown(f"### ✏️ Editando: **{row_data['Cliente']}** ({row_data['Fecha'].strftime('%d/%m')})")
            
            with st.form("form_edicion"):
                c1, c2, c3, c4 = st.columns(4)
                e_kgc = c1.number_input("Kg Compra", value=float(row_data['Kg_Compra']))
                e_pc = c2.number_input("Precio Compra", value=float(row_data['Precio_Compra']))
                e_plaza = c3.number_input("Precio Plaza (Ref)", value=float(row_data['Precio_Plaza'])) # Editable
                e_kgv = c4.number_input("Kg Venta", value=float(row_data['Kg_Venta']))
                
                c5, c6 = st.columns(2)
                e_pv = c5.number_input("Precio Venta", value=float(row_data['Precio_Venta']))
                e_est = c6.selectbox("Estado", ["Pagado", "Pendiente"], index=0 if row_data['Estado_Pago'] == "Pagado" else 1)
                
                st.caption("Archivos:")
                col_fa, col_fb = st.columns(2)
                e_file_c = col_fa.file_uploader("Nueva Fac. Compra")
                e_file_v = col_fb.file_uploader("Nueva Fac. Venta")

                if st.form_submit_button("💾 Guardar Cambios"):
                    gastos = row_data['Fletes'] + row_data['Descuentos'] + row_data['Viaticos'] + row_data['Otros_Gastos']
                    new_util = (e_kgv * e_pv) - (e_kgc * e_pc) - gastos

                    updates = {
                        "kg_compra": e_kgc, "precio_compra": e_pc,
                        "kg_venta": e_kgv, "precio_venta": e_pv,
                        "precio_plaza": e_plaza, # Actualizamos plaza
                        "estado_pago": e_est,
                        "utilidad": new_util
                    }
                    
                    if e_file_c:
                        updates["fec_doc_url"] = subir_archivo(e_file_c, f"edit_compra_{row_data['Proveedor']}")
                    if e_file_v:
                        updates["fev_doc_url"] = subir_archivo(e_file_v, f"edit_venta_{row_data['Cliente']}")
                    
                    supabase.table("ventas_2026").update(updates).eq("id", int(id_row)).execute()
                    st.cache_data.clear()
                    st.success("✅ Actualizado.")
                    st.rerun()
            
            if st.button("🗑️ Eliminar Registro", type="primary"):
                supabase.table("ventas_2026").delete().eq("id", int(id_row)).execute()
                st.cache_data.clear()
                st.warning("Registro eliminado.")
                st.rerun()
    else:
        st.write("No hay registros.")












