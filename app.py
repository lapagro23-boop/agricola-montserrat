import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta, datetime
from supabase import create_client
import io
import re
import unicodedata

# --- 1. CONFIGURACIÓN E INYECCIÓN CSS ---
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
    div[data-testid="stMetricLabel"] { color: #388e3c; font-weight: bold; }
    .stButton>button {
        background-color: #2e7d32; color: white; border-radius: 8px; border: none;
        padding: 10px 20px; font-weight: bold;
    }
    .stButton>button:hover { background-color: #1b5e20; color: white; }
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e0e0e0; }
    </style>
""", unsafe_allow_html=True)

# --- SEGURIDAD ---
def check_password():
    if st.session_state.get("password_input") == st.secrets["APP_PASSWORD"]:
        st.session_state["password_correct"] = True
        del st.session_state["password_input"]
    else: st.error("😕 Clave incorrecta.")

if not st.session_state.get("password_correct", False):
    st.title("🔐 Acceso Restringido")
    st.text_input("Ingresa la clave maestra:", type="password", key="password_input", on_change=check_password)
    st.stop()

# --- CONEXIÓN SUPABASE ---
try:
    supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    BUCKET_FACTURAS = "facturas"
except:
    st.error("⚠️ Error de conexión.")
    st.stop()

# --- FUNCIONES ---

def limpiar_nombre(nombre):
    nombre = unicodedata.normalize('NFKD', nombre).encode('ASCII', 'ignore').decode('utf-8')
    nombre = nombre.replace(" ", "_")
    return re.sub(r'[^\w.-]', '', nombre)

def subir_archivo(archivo, nombre_base):
    if archivo:
        try:
            ext = archivo.name.split('.')[-1]
            path = f"{limpiar_nombre(nombre_base)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
            supabase.storage.from_(BUCKET_FACTURAS).upload(path, archivo.getvalue(), {"content-type": archivo.type, "upsert": "true"})
            return supabase.storage.from_(BUCKET_FACTURAS).get_public_url(path)
        except: return None
    return None

@st.cache_data(ttl=5) 
def cargar_datos():
    # 1. Ventas
    df_v = pd.DataFrame()
    try:
        res = supabase.table("ventas_2026").select("*").order("fecha", desc=True).execute()
        df_v = pd.DataFrame(res.data)
        if not df_v.empty:
            cols = {
                'id': 'ID', 'fecha': 'Fecha', 'producto': 'Producto', 'proveedor': 'Proveedor', 
                'cliente': 'Cliente', 'fec_doc_url': 'FEC_Doc', 'fev_doc_url': 'FEV_Doc', 
                'kg_compra': 'Kg_Compra', 'precio_compra': 'Precio_Compra', 'fletes': 'Fletes',
                'kg_venta': 'Kg_Venta', 'precio_venta': 'Precio_Venta', 'descuentos': 'Descuentos',
                'utilidad': 'Utilidad', 'estado_pago': 'Estado_Pago', 'dias_credito': 'Dias_Credito',
                'precio_plaza': 'Precio_Plaza'
            }
            df_v = df_v.rename(columns={k: v for k, v in cols.items() if k in df_v.columns})
            df_v['Fecha'] = pd.to_datetime(df_v['Fecha'])
            # Asegurar columnas numéricas
            for c in ['Kg_Compra','Precio_Compra','Fletes','Kg_Venta','Precio_Venta','Descuentos','Utilidad','Precio_Plaza']:
                if c in df_v.columns: df_v[c] = pd.to_numeric(df_v[c]).fillna(0.0)
    except: pass

    # 2. Gastos
    df_g = pd.DataFrame()
    try:
        res_g = supabase.table("gastos_fijos_2026").select("*").order("fecha", desc=True).execute()
        df_g = pd.DataFrame(res_g.data)
        if not df_g.empty:
            df_g = df_g.rename(columns={'id': 'ID', 'fecha': 'Fecha', 'concepto': 'Concepto', 'monto': 'Monto'})
            df_g['Fecha'] = pd.to_datetime(df_g['Fecha'])
            df_g['Monto'] = pd.to_numeric(df_g['Monto']).fillna(0.0)
    except: pass

    # 3. Saldo Inicial
    saldo_ini = 0.0
    try:
        res_c = supabase.table("configuracion_caja").select("saldo_inicial").limit(1).execute()
        if res_c.data: saldo_ini = float(res_c.data[0]['saldo_inicial'])
    except: pass

    return df_v, df_g, saldo_ini

def color_deuda(row):
    color = ''
    try:
        if row['Estado_Pago'] == 'Pagado': color = 'background-color: #e8f5e9; color: #1b5e20; font-weight: bold;'
        elif row['Estado_Pago'] == 'Pendiente':
            dias = int(row['Dias_Credito']) if pd.notnull(row['Dias_Credito']) else 0
            vence = row['Fecha'] + timedelta(days=dias)
            if (vence.date() - date.today()).days < 0: color = 'background-color: #ffebee; color: #b71c1c; font-weight: bold;'
            elif (vence.date() - date.today()).days <= 3: color = 'background-color: #fff8e1; color: #f57f17; font-weight: bold;'
    except: pass
    return [color] * len(row)

def obtener_opciones(df, col, defaults):
    existentes = df[col].unique().tolist() if not df.empty and col in df.columns else []
    return sorted(list(set(defaults + [x for x in existentes if x])))

# --- INTERFAZ ---
st.markdown("# 🍌 Agrícola Montserrat")
st.markdown("### _Sistema de Gestión Integral 2026_")
st.divider()

# SIDEBAR
st.sidebar.title("Menú")
if st.sidebar.button("🔄 Actualizar Datos"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.divider()
f_ini = st.sidebar.date_input("📅 Inicio", date(2026, 1, 1))
f_fin = st.sidebar.date_input("📅 Fin", date(2026, 12, 31))

# CARGA DE DATOS
df_v, df_g, saldo_inicial = cargar_datos()

# --- LÓGICA DE CAJA (ANTES DE MOSTRAR SIDEBAR) ---
ingresos_caja = 0
egresos_caja = 0

if not df_v.empty:
    # Entradas: Solo Ventas PAGADAS
    # Valor entrada = KgVenta * PrecioVenta (Bruto)
    ventas_pagadas = df_v[df_v['Estado_Pago'] == 'Pagado']
    ingresos_caja = (ventas_pagadas['Kg_Venta'] * ventas_pagadas['Precio_Venta']).sum()
    
    # Salidas: Compras + Fletes (TODOS, se asume contado)
    compras_total = (df_v['Kg_Compra'] * df_v['Precio_Compra']).sum()
    fletes_total = df_v['Fletes'].sum()
    egresos_caja += compras_total + fletes_total

if not df_g.empty:
    egresos_caja += df_g['Monto'].sum()

# Cálculo actual del sistema
flujo_acumulado = ingresos_caja - egresos_caja
caja_sistema = saldo_inicial + flujo_acumulado

# CONFIGURACIÓN CAJA (Calibración)
st.sidebar.divider()
st.sidebar.subheader("💰 Calibrar Caja")
with st.sidebar.form("config_caja"):
    st.caption(f"El sistema calcula: ${caja_sistema:,.0f}")
    valor_real_usuario = st.number_input("¿Cuánto tienes REALMENTE hoy?", value=float(caja_sistema), format="%.2f")
    
    if st.form_submit_button("✅ Ajustar a Realidad"):
        # Matemática inversa: Si Caja_Real = Base + Flujo
        # Entonces: Nueva_Base = Caja_Real - Flujo
        nueva_base = valor_real_usuario - flujo_acumulado
        supabase.table("configuracion_caja").update({"saldo_inicial": nueva_base}).gt("id", 0).execute()
        st.cache_data.clear()
        st.success("¡Caja Calibrada!")
        st.rerun()

# FILTROS
df_vf = df_v[(df_v['Fecha'].dt.date >= f_ini) & (df_v['Fecha'].dt.date <= f_fin)].copy() if not df_v.empty else pd.DataFrame()
df_gf = df_g[(df_g['Fecha'].dt.date >= f_ini) & (df_g['Fecha'].dt.date <= f_fin)].copy() if not df_g.empty else pd.DataFrame(columns=['ID','Fecha','Concepto','Monto'])

# ALERTAS
if not df_v.empty:
    pend = df_v[df_v['Estado_Pago'] == 'Pendiente'].copy()
    if not pend.empty:
        pend['Dias_Credito'] = pd.to_numeric(pend['Dias_Credito'], errors='coerce').fillna(0)
        pend['Vence'] = pend['Fecha'] + pd.to_timedelta(pend['Dias_Credito'], unit='D')
        hoy_ts = pd.Timestamp.now().normalize()
        mask_urg = (pend['Vence'] - hoy_ts).dt.days <= 3
        urg = pend[mask_urg]
        if not urg.empty: st.error(f"🔔 Tienes {len(urg)} facturas críticas por cobrar.")

# PESTAÑAS
t1, t_ana, t_gas, t2, t3 = st.tabs(["📊 Dashboard", "📈 Analítica", "💸 Gastos", "🧮 Nueva Op.", "🚦 Cartera (Editar)"])

# --- DASHBOARD ---
with t1:
    st.subheader("Estado Financiero")
    ub = df_vf['Utilidad'].sum() if not df_vf.empty else 0
    vol = df_vf['Kg_Venta'].sum() if not df_vf.empty else 0
    
    c1, c2, c3 = st.columns(3)
    # Mostramos la caja calibrada (que es igual a caja_sistema tras recargar)
    c1.metric("💰 CAJA REAL (DISPONIBLE)", f"${caja_sistema:,.0f}", delta="Efectivo en mano")
    c2.metric("Utilidad Periodo", f"${ub:,.0f}", delta="Rentabilidad")
    c3.metric("Volumen Movido", f"{vol:,.1f} Kg")
    
    st.info(f"💡 **Flujo:** Cobros (${ingresos_caja:,.0f}) - Pagos/Gastos (${egresos_caja:,.0f}) + Base Ajustada")

# --- ANALÍTICA ---
with t_ana:
    if not df_vf.empty:
        df_p = df_vf[df_vf['Precio_Plaza'] > 0].sort_values("Fecha")
        c1, c2 = st.columns([3,1])
        with c1:
            if not df_p.empty:
                # Gráfica corregida y segura
                fig = px.line(df_p, x='Fecha', y=['Precio_Compra', 'Precio_Plaza'], markers=True, title="Precios: Compra vs Plaza")
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("Faltan datos de plaza.")
        with c2:
            if not df_p.empty:
                ahorro = df_p['Precio_Plaza'].mean() - df_p['Precio_Compra'].mean()
                st.metric("Margen vs Plaza", f"${ahorro:,.0f}", delta="Ahorro/Kg" if ahorro>0 else "Sobrecosto")

# --- GASTOS ---
with t_gas:
    with st.form("add_gasto", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        fg = c1.date_input("Fecha", date.today())
        cg = c2.text_input("Concepto")
        mg = c3.number_input("Valor", min_value=0.0, format="%.2f")
        if st.form_submit_button("Registrar Gasto"):
            if cg and mg > 0:
                supabase.table("gastos_fijos_2026").insert({"fecha": str(fg), "concepto": cg, "monto": mg}).execute()
                st.cache_data.clear()
                st.rerun()
    if not df_gf.empty:
        st.dataframe(df_gf.style.format({"Monto": "${:,.2f}"}), use_container_width=True, hide_index=True)
        with st.expander("Borrar Gasto"):
            idg = st.number_input("ID Gasto", step=1)
            if st.button("Eliminar"):
                supabase.table("gastos_fijos_2026").delete().eq("id", idg).execute()
                st.cache_data.clear()
                st.rerun()

# --- NUEVA OPERACIÓN ---
with t2:
    with st.form("add_viaje", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        fin = c1.date_input("Fecha", date.today())
        
        prod = c2.selectbox("Fruta", obtener_opciones(df_v, 'Producto', ["Plátano", "Guayabo"]))
        n_prod = c2.text_input("¿Otra fruta?", placeholder="Opcional")
        prov = c3.selectbox("Proveedor", obtener_opciones(df_v, 'Proveedor', ["Omar", "Rancho"]))
        n_prov = c3.text_input("¿Otro prov?", placeholder="Opcional")
        cli = c4.selectbox("Cliente", obtener_opciones(df_v, 'Cliente', ["Calima", "Fogón"]))
        n_cli = c4.text_input("¿Otro cli?", placeholder="Opcional")

        cc, cv = st.columns(2)
        with cc:
            st.markdown("##### 🛒 Compra (Salida Caja)")
            kgc = st.number_input("Kg Compra", min_value=0.0, format="%.2f")
            pc = st.number_input("Precio Compra", min_value=0.0, format="%.2f")
            pplaza = st.number_input("Precio Plaza", min_value=0.0, format="%.2f")
            fl = st.number_input("Fletes", min_value=0.0, format="%.2f")
            file_c = st.file_uploader("Factura Compra")
        with cv:
            st.markdown("##### 🤝 Venta (Entrada si Pagado)")
            kgv = st.number_input("Kg Venta", min_value=0.0, format="%.2f")
            pv = st.number_input("Precio Venta", min_value=0.0, format="%.2f")
            desc = st.number_input("Deducciones", min_value=0.0, format="%.2f")
            file_v = st.file_uploader("Factura Venta")

        uest = (kgv * pv) - (kgc * pc) - fl - desc
        st.info(f"Utilidad Estimada: ${uest:,.2f}")
        
        est = st.selectbox("Estado", ["Pagado", "Pendiente"])
        dias = st.number_input("Días Crédito", 8)

        if st.form_submit_button("Guardar Viaje"):
            f_prod, f_prov, f_cli = n_prod or prod, n_prov or prov, n_cli or cli
            if f_prov and f_cli:
                with st.spinner("Guardando..."):
                    uc = subir_archivo(file_c, f"c_{f_prov}")
                    uv = subir_archivo(file_v, f"v_{f_cli}")
                    data = {
                        "fecha": str(fin), "producto": f_prod, "proveedor": f_prov, "cliente": f_cli,
                        "kg_compra": kgc, "precio_compra": pc, "fletes": fl, "kg_venta": kgv, "precio_venta": pv, 
                        "descuentos": desc, "utilidad": uest, "estado_pago": est, "dias_credito": dias, 
                        "precio_plaza": pplaza, "fec_doc_url": uc if uc else "", "fev_doc_url": uv if uv else ""
                    }
                    supabase.table("ventas_2026").insert(data).execute()
                    st.cache_data.clear()
                    st.success("Registrado!")
                    st.rerun()

# --- CARTERA (EDICIÓN) ---
with t3:
    if not df_vf.empty:
        col_conf = {
            "FEC_Doc": st.column_config.LinkColumn("F.C", display_text="Ver"),
            "FEV_Doc": st.column_config.LinkColumn("F.V", display_text="Ver"),
            "Fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
            "Utilidad": st.column_config.NumberColumn("Utilidad", format="$%d"),
        }
        
        evt = st.dataframe(
            df_vf.style.apply(color_deuda, axis=1),
            use_container_width=True, column_config=col_conf,
            selection_mode="single-row", on_select="rerun", hide_index=True
        )
        
        if evt.selection.rows:
            row = df_vf.iloc[evt.selection.rows[0]]
            st.divider()
            st.markdown(f"### ✏️ Editando registro de: **{row['Fecha'].strftime('%d-%b')}**")
            
            with st.form("edit_full"):
                c1, c2, c3, c4 = st.columns(4)
                e_fecha = c1.date_input("Fecha Original", value=pd.to_datetime(row['Fecha']).date())
                e_cli = c2.text_input("Cliente", value=row['Cliente'])
                e_prov = c3.text_input("Proveedor", value=row['Proveedor'])
                e_prod = c4.text_input("Producto", value=row['Producto'])
                
                st.markdown("**Datos Compra**")
                cc1, cc2, cc3, cc4 = st.columns(4)
                e_kgc = cc1.number_input("Kg Compra", value=float(row['Kg_Compra']), format="%.2f")
                e_pc = cc2.number_input("Precio Compra", value=float(row['Precio_Compra']), format="%.2f")
                e_plaza = cc3.number_input("Precio Plaza", value=float(row['Precio_Plaza']), format="%.2f")
                e_fletes = cc4.number_input("Fletes", value=float(row.get('Fletes', 0.0)), format="%.2f")

                st.markdown("**Datos Venta**")
                cv1, cv2, cv3, cv4 = st.columns(4)
                e_kgv = cv1.number_input("Kg Venta", value=float(row['Kg_Venta']), format="%.2f")
                e_pv = cv2.number_input("Precio Venta", value=float(row['Precio_Venta']), format="%.2f")
                e_desc = cv3.number_input("Deducciones", value=float(row.get('Descuentos', 0.0)), format="%.2f")
                e_est = cv4.selectbox("Estado Pago", ["Pagado", "Pendiente"], index=0 if row['Estado_Pago']=="Pagado" else 1)
                
                if st.form_submit_button("💾 Guardar Cambios Completos"):
                    nu = (e_kgv * e_pv) - (e_kgc * e_pc) - e_fletes - e_desc
                    
                    supabase.table("ventas_2026").update({
                        "fecha": str(e_fecha),
                        "cliente": e_cli, "proveedor": e_prov, "producto": e_prod,
                        "kg_compra": e_kgc, "precio_compra": e_pc, "precio_plaza": e_plaza, "fletes": e_fletes,
                        "kg_venta": e_kgv, "precio_venta": e_pv, "descuentos": e_desc,
                        "estado_pago": e_est, "utilidad": nu
                    }).eq("id", int(row['ID'])).execute()
                    
                    st.cache_data.clear()
                    st.success("Registro actualizado correctamente.")
                    st.rerun()
            
            if st.button("🗑️ Borrar Registro Definitivamente"):
                supabase.table("ventas_2026").delete().eq("id", int(row['ID'])).execute()
                st.cache_data.clear()
                st.rerun()
