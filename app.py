import streamlit as st
from supabase import create_client
import pandas as pd

st.title("🕵️ Modo Diagnóstico: Agrícola Montserrat")

# 1. VERIFICACIÓN DE CREDENCIALES
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    
    st.write("---")
    st.info("1. Verificando Secretos...")
    st.write(f"**URL:** `{url}`") # Veremos si la URL tiene espacios o errores
    st.write(f"**KEY:** `{key[:10]}...` (Oculta por seguridad)")
    
    if " " in url:
        st.error("🚨 ALERTA: La URL contiene espacios en blanco. ¡Debes borrarlos en los Secrets!")
    else:
        st.success("✅ Formato de URL parece correcto (sin espacios).")

    # 2. CONEXIÓN AL CLIENTE
    supabase = create_client(url, key)
    st.success("✅ Cliente de Supabase creado.")

except Exception as e:
    st.error(f"❌ Error grave leyendo los secrets: {e}")
    st.stop()

# 3. INTENTO DE LECTURA DE TABLA
st.write("---")
st.info("2. Intentando conectar con la tabla 'ventas_2026'...")

try:
    # Intentamos leer solo 1 fila para ver si entra
    response = supabase.table("ventas_2026").select("*").limit(1).execute()
    
    st.success("🎉 ¡CONEXIÓN EXITOSA! La tabla existe y responde.")
    st.write("Datos recibidos:", response.data)

except Exception as e:
    st.error("❌ ERROR CRÍTICO DE BASE DE DATOS:")
    
    # Imprimimos el error crudo para verlo todo
    st.code(str(e))
    
    # Intentamos desglosar el mensaje si viene de la API
    try:
        if hasattr(e, 'code'): st.write(f"👉 **Código:** {e.code}")
        if hasattr(e, 'message'): st.write(f"👉 **Mensaje:** {e.message}")
        if hasattr(e, 'details'): st.write(f"👉 **Detalles:** {e.details}")
        if hasattr(e, 'hint'): st.write(f"👉 **Pista:** {e.hint}")
    except:
        pass
