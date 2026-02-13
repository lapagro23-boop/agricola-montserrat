"""
Script temporal para cargar datos 2025 a Supabase
EJECUTAR UNA SOLA VEZ desde Streamlit
Después BORRAR este archivo
"""

import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime

st.title("🔄 Cargar Datos 2025 a Supabase")
st.warning("⚠️ Este script se ejecuta UNA SOLA VEZ. Después debes borrarlo del repositorio.")

# Subir CSV
uploaded_file = st.file_uploader("Sube el archivo AM_2025.csv", type=['csv'])

if uploaded_file and st.button("🚀 CARGAR DATOS A SUPABASE"):
    
    with st.spinner("Procesando..."):
        
        try:
            # Conectar a Supabase
            supabase = create_client(
                st.secrets["SUPABASE_URL"],
                st.secrets["SUPABASE_KEY"]
            )
            st.success("✅ Conectado a Supabase")
            
            # Leer CSV
            df = pd.read_csv(uploaded_file)
            st.info(f"📄 CSV leído: {len(df)} filas")
            
            # Función para limpiar moneda
            def limpiar_moneda(valor):
                if pd.isna(valor) or valor == '':
                    return 0.0
                if isinstance(valor, str):
                    valor = valor.replace('$', '').replace(',', '').replace(' ', '')
                    try:
                        return float(valor)
                    except:
                        return 0.0
                return float(valor)
            
            # Función para normalizar cliente
            def normalizar_cliente(cliente):
                if pd.isna(cliente) or cliente == '':
                    return None
                if 'Fogón' in str(cliente) or 'Fogoón' in str(cliente):
                    return 'Fogón del Mar'
                return str(cliente).strip()
            
            # Limpiar datos
            st.info("🔄 Limpiando datos...")
            
            df['Fecha'] = pd.to_datetime(df['Fecha'], format='%d/%m/%Y', errors='coerce')
            
            # Limpiar columnas monetarias
            columnas_moneda = [
                'Precio de Compra', 'Costo Bruto ', 'Viáticos', 'Flete', 
                'Otros Gastos', 'Costo Neto', 'Precio de Venta', 
                'Utilidad bruta', 'RETENCIONES', 'Descuentos', 'Utilidad neta'
            ]
            
            for col in columnas_moneda:
                if col in df.columns:
                    df[col] = df[col].apply(limpiar_moneda)
            
            # Limpiar cantidades
            if 'Cantidad (Kg)' in df.columns:
                df['Cantidad (Kg)'] = pd.to_numeric(df['Cantidad (Kg)'], errors='coerce').fillna(0)
            if 'Cantidad (kg)' in df.columns:
                df['Cantidad (kg)'] = pd.to_numeric(df['Cantidad (kg)'], errors='coerce').fillna(0)
            
            # Normalizar clientes
            if 'Cliente' in df.columns:
                df['Cliente'] = df['Cliente'].apply(normalizar_cliente)
            
            # Filtrar válidos
            df_valido = df[df['Fecha'].notna()].copy()
            st.success(f"✅ {len(df_valido)} filas válidas")
            
            # Preparar registros
            st.info("🔄 Preparando datos...")
            registros = []
            
            for idx, row in df_valido.iterrows():
                try:
                    registro = {
                        'fecha': row['Fecha'].strftime('%Y-%m-%d'),
                        'proveedor': str(row.get('Proveedor', '')).strip() if pd.notna(row.get('Proveedor')) else None,
                        'cliente': normalizar_cliente(row.get('Cliente')),
                        'producto': str(row.get('Producto', '')).strip() if pd.notna(row.get('Producto')) else None,
                        'kg_compra': float(row.get('Cantidad (Kg)', 0)),
                        'precio_compra': float(row.get('Precio de Compra', 0)),
                        'viaticos': float(row.get('Viáticos', 0)),
                        'fletes': float(row.get('Flete', 0)),
                        'otros_gastos': float(row.get('Otros Gastos', 0)),
                        'kg_venta': float(row.get('Cantidad (kg)', 0)),
                        'precio_venta': float(row.get('Precio de Venta', 0)),
                        'retenciones': float(row.get('RETENCIONES', 0)),
                        'descuentos': float(row.get('Descuentos', 0)),
                        'utilidad_neta': float(row.get('Utilidad neta', 0))
                    }
                    registros.append(registro)
                except Exception as e:
                    st.warning(f"⚠️ Error en fila {idx}: {e}")
                    continue
            
            st.success(f"✅ {len(registros)} registros preparados")
            
            # Insertar en lotes
            st.info("🔄 Insertando en Supabase...")
            
            progress_bar = st.progress(0)
            batch_size = 100
            total_insertados = 0
            errores = 0
            
            for i in range(0, len(registros), batch_size):
                batch = registros[i:i+batch_size]
                try:
                    supabase.table('ventas_2025').insert(batch).execute()
                    total_insertados += len(batch)
                    progress_bar.progress(min(total_insertados / len(registros), 1.0))
                except Exception as e:
                    errores += len(batch)
                    st.error(f"❌ Error en batch: {e}")
            
            # Resumen
            st.divider()
            st.markdown("### 📊 RESUMEN")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Total CSV", len(df))
            col2.metric("Insertados", total_insertados)
            col3.metric("Errores", errores)
            
            if total_insertados > 0:
                st.balloons()
                st.success(f"✅ ¡Carga completada! {(total_insertados/len(df_valido)*100):.1f}% éxito")
                st.info("Ahora puedes BORRAR este archivo del repositorio y usar la app normalmente.")
            else:
                st.error("❌ No se pudo cargar ningún dato")
                
        except Exception as e:
            st.error(f"❌ Error general: {e}")

st.divider()
st.caption("⚠️ Después de ejecutar exitosamente, BORRA este archivo del repositorio GitHub")
