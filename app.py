import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta, datetime
from supabase import create_client
import io
import re
import unicodedata

# --- 1. CONFIGURACIÓN ---
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

# --- CONEXIÓN ---
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
            for c in ['Kg_Compra','Precio_Compra','Fletes','Kg_Venta','Precio_Venta','Descuentos','Utilidad','Precio_Plaza']:
                if c in df_v.columns: df_v[c] = pd.to_numeric(df_v[c]).fillna(0.0)
    except: pass

    # 2. Movimientos Caja (Antiguos Gastos)
    df_g = pd.DataFrame()
    try:
        res_g = supabase.table("gastos_fijos_2026").select("*").order("fecha", desc=True).execute()
        df_g = pd.DataFrame(res_g.data)
        if not df_g.empty:
            # Ahora traemos 'tipo' también
            df_g = df_g.rename(columns={'id': 'ID', 'fecha': 'Fecha', 'concepto': 'Concepto', 'monto': 'Monto', 'tipo': 'Tipo'})
            df_g['Fecha'] = pd.to_datetime(df_g['Fecha'])
            df_g['Monto'] = pd.to_numeric(df_g['Monto']).fillna(0.0)
            if 'Tipo' not in df_g.columns: df_g['Tipo'] = 'Gasto' # Default para datos viejos
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

st.sidebar.title("Menú")
if st.sidebar.button("🔄 Actualizar Datos"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.divider()
f_ini = st.sidebar.date_input("📅 Inicio", date(2026, 1, 1))
f_fin = st.sidebar.date_input("📅 Fin", date(2026, 12, 31))

# CARGA DATOS
df_v, df_g, saldo_inicial = cargar_datos()

# --- LÓGICA FINANCIERA ---
ingresos_caja = 0
egresos_caja = 0
gastos_operativos_total = 0

if not df_v.empty:
    # 1. Operación Fruta
    ventas_pagadas = df_v[df_v['Estado_Pago'] == 'Pagado']
    ingresos_caja += (ventas_pagadas['Kg_Venta'] * ventas_pagadas['Precio_Venta']).sum()
    
    compras_total = (df_v['Kg_Compra'] * df_v['Precio_Compra']).sum()
    fletes_total = df_v['Fletes'].sum()
    egresos_caja += compras_total + fletes_total

if not df_g.empty:
    # 2. Movimientos Extra
    # Gasto: Resta Caja, Resta Utilidad
    gastos = df_g[df_g['Tipo'] == 'Gasto']
    gastos_val = gastos['Monto'].sum()
    egresos_caja += gastos_val
    gastos_operativos_total = gastos_val

    # Préstamo Salida: Resta Caja, NO afecta Utilidad
    prestamos_out = df_g[df_g['Tipo'] == 'Préstamo Salida']
    egresos_caja += prestamos_out['Monto'].sum()

    # Ingreso Extra: Suma Caja, NO afecta Utilidad Operativa (o podríamos separarlo)
    ingresos_in = df_g[df_g['Tipo'] == 'Ingreso Extra']
    ingresos_caja += ingresos_in['Monto'].sum()

flujo_acumulado = ingresos_caja - egresos_caja
caja_sistema = saldo_inicial + flujo_acumulado

# CALIBRACIÓN
st.sidebar.divider()
st.sidebar.subheader("💰 Calibrar Caja")
with st.sidebar.form("config_caja"):
    st.caption(f"Sistema: ${caja_sistema:,.0f}")
    valor_real = st.number_input("Realidad HOY:", value=float(caja_sistema), format="%.2f")
    if st.form_submit_button("✅ Ajustar"):
        nueva_base = valor_real - flujo_acumulado
        supabase.table("configuracion_caja").update({"saldo_inicial": nueva_base}).gt("id", 0).execute()
        st.cache_data.clear()
        st.rerun()

# FILTROS
df_vf = df_v[(df_v['Fecha'].dt.date >= f_ini) & (df_v['Fecha'].dt.date <= f_fin)].copy() if not df_v.empty else pd.DataFrame()
df_gf = df_g[(df_g['Fecha'].dt.date >= f_ini) & (df_g['Fecha'].dt.date <= f_fin)].copy() if not df_g.empty else pd.DataFrame(columns=['ID','Fecha','Concepto','Monto','Tipo'])

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
t1, t_ana, t_mov, t2, t3 = st.tabs(["📊 Dashboard", "📈 Analítica", "💸 Movimientos (Caja)", "🧮 Nueva Op.", "🚦 Cartera"])

# --- DASHBOARD ---
with t1:
    st.subheader("Estado Financiero")
    # Utilidad = (Ventas - Compras - Fletes) - GASTOS OPERATIVOS (No préstamos)
    util_bruta_viajes = df_vf['Utilidad'].sum() if not df_vf.empty else 0
    
    # Filtramos gastos operativos del rango de fechas
    gastos_per = df_gf[df_gf['Tipo'] == 'Gasto']['Monto'].sum() if not df_gf.empty else 0
    
    util_neta = util_bruta_viajes - gastos_per
    vol = df_vf['Kg_Venta'].sum() if not df_vf.empty else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("💰 CAJA REAL", f"${caja_sistema:,.0f}", delta="Efectivo Disponible")
    c2.metric("Utilidad Neta", f"${util_neta:,.0f}", delta="Ganancia Real (Sin gastos)")
    c3.metric("Volumen", f"{vol:,.1f} Kg")
    
    st.info("ℹ️ **Nota:** Los 'Préstamos' afectan la Caja pero NO reducen tu Utilidad Neta.")

# --- ANALÍTICA ---
with t_ana:
    if not df_vf.empty:
        df_p = df_vf[df_vf['Precio_Plaza'] > 0].sort_values("Fecha")
        c1, c2 = st.columns([3,1])
        with c1:
            if not df_p.empty:
                fig = px.line(df_p, x='Fecha', y=['Precio_Compra', 'Precio_Plaza'], markers=True, title="Precios: Compra vs Plaza")
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("Faltan datos de plaza.")
        with c2:
            if not df_p.empty:
                ahorro = df_p['Precio_Plaza'].mean() - df_p['Precio_Compra'].mean()
                st.metric("Margen vs Plaza", f"${ahorro:,.0f}", delta="Ahorro/Kg" if ahorro>0 else "Sobrecosto")

# --- MOVIMIENTOS CAJA ---
with t_mov:
    st.subheader("💸 Registro de Movimientos")
    with st.form("add_mov", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        fm = c1.date_input("Fecha", date.today())
        cm = c2.text_input("Concepto / Comentario")
        tm = c3.selectbox("Tipo", ["Gasto (Gasolina/Nómina)", "Préstamo Salida (Prestar)", "Ingreso Extra (Devolución/Aporte)"])
        mm = c4.number_input("Valor ($)", min_value=0.0, format="%.2f")
        
        if st.form_submit_button("Registrar"):
            tipo_db = "Gasto"
            if "Préstamo" in tm: tipo_db = "Préstamo Salida"
            elif "Ingreso" in tm: tipo_db = "Ingreso Extra"
            
            if cm and mm > 0:
                supabase.table("gastos_fijos_2026").insert({"fecha": str(fm), "concepto": cm, "monto": mm, "tipo": tipo_db}).execute()
                st.cache_data.clear()
                st.rerun()

    if not df_gf.empty:
        # Colorear fila según tipo
        def color_mov(row):
            if row['Tipo'] == 'Gasto': return ['background-color: #ffebee']*len(row) # Rojo claro
            if row['Tipo'] == 'Préstamo Salida': return ['background-color: #e3f2fd']*len(row) # Azul claro
            if row['Tipo'] == 'Ingreso Extra': return ['background-color: #e8f5e9']*len(row) # Verde claro
            return ['']*len(row)

        st.dataframe(df_gf.style.apply(color_mov, axis=1).format({"Monto": "${:,.2f}"}), use_container_width=True, hide_index=True)
        with st.expander("Borrar Movimiento"):
            idg = st.number_input("ID a borrar", step=1)
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
            st.markdown("##### 🛒 Compra")
            kgc = st.number_input("Kg Compra", min_value=0.0, format="%.2f")
            pc = st.number_input("Precio Compra", min_value=0.0, format="%.2f")
            pplaza = st.number_input("Precio Plaza", min_value=0.0, format="%.2f")
            fl = st.number_input("Fletes", min_value=0.0, format="%.2f")
            file_c = st.file_uploader("Factura Compra")
        with cv:
            st.markdown("##### 🤝 Venta")
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

# --- CARTERA ---
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
            st.markdown(f"### ✏️ Editando: **{row['Fecha'].strftime('%d-%b')}**")
            
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
                
                st.markdown("**Soportes (Subir para reemplazar)**")
                cf1, cf2 = st.columns(2)
                new_file_c = cf1.file_uploader("Nueva F.Compra")
                new_file_v = cf2.file_uploader("Nueva F.Venta")

                if st.form_submit_button("💾 Guardar Cambios"):
                    nu = (e_kgv * e_pv) - (e_kgc * e_pc) - e_fletes - e_desc
                    updates = {
                        "fecha": str(e_fecha), "cliente": e_cli, "proveedor": e_prov, "producto": e_prod,
                        "kg_compra": e_kgc, "precio_compra": e_pc, "precio_plaza": e_plaza, "fletes": e_fletes,
                        "kg_venta": e_kgv, "precio_venta": e_pv, "descuentos": e_desc,
                        "estado_pago": e_est, "utilidad": nu
                    }
                    if new_file_c:
                        u = subir_archivo(new_file_c, f"e_c_{e_prov}")
                        if u: updates["fec_doc_url"] = u
                    if new_file_v:
                        u = subir_archivo(new_file_v, f"e_v_{e_cli}")
                        if u: updates["fev_doc_url"] = u

                    supabase.table("ventas_2026").update(updates).eq("id", int(row['ID'])).execute()
                    st.cache_data.clear()
                    st.success("Actualizado")
                    st.rerun()
            
            if st.button("🗑️ Borrar"):
                supabase.table("ventas_2026").delete().eq("id", int(row['ID'])).execute()
                st.cache_data.clear()
                st.rerun()
