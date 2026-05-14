import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import re
import time

# --- CONFIGURACIÓN ESTÉTICA ---
st.set_page_config(page_title="Lavandería Master Pro v4.0", layout="wide", page_icon="🧺")

# --- CONEXIÓN A BASE DE DATOS ---
conn = sqlite3.connect('sistema_lavanderia_v4.db', check_same_thread=False)
c = conn.cursor()

def inicializar_db():
    c.execute('CREATE TABLE IF NOT EXISTS usuarios (usuario TEXT PRIMARY KEY, clave TEXT, rol TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS clientes 
                 (id INTEGER PRIMARY KEY, nombre TEXT, tel TEXT, lat REAL, lon REAL, notas TEXT, fecha_registro DATETIME)''')
    c.execute('CREATE TABLE IF NOT EXISTS lavadoras (id INTEGER PRIMARY KEY, serie TEXT, modelo TEXT, estado TEXT)')
    c.execute('''CREATE TABLE IF NOT EXISTS alquileres_activos 
                 (id INTEGER PRIMARY KEY, id_cliente INTEGER, id_lavadora INTEGER, inicio DATETIME, fin DATETIME, 
                  horas_extras INTEGER DEFAULT 0, avisado INTEGER DEFAULT 0, repartidor_asig TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS historial_alquileres 
                 (id INTEGER PRIMARY KEY, id_cliente INTEGER, id_lavadora INTEGER, fecha DATETIME, 
                  monto REAL, tipo_pago TEXT, referencia TEXT, usuario_cobro TEXT)''')
    c.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, usuario TEXT, accion TEXT, fecha DATETIME)')
    c.execute("INSERT OR IGNORE INTO usuarios VALUES ('admin', 'admin123', 'Admin'), ('cajera', 'caja123', 'Cajera'), ('repartidor', 'ruta123', 'Repartidor')")
    conn.commit()

inicializar_db()

def registrar_log(accion):
    user = st.session_state.get('user', 'Sistema')
    c.execute("INSERT INTO logs (usuario, accion, fecha) VALUES (?,?,?)", (user, accion, datetime.now()))
    conn.commit()

# --- ESTADO DE SESIÓN ---
if 'radio_despacho' not in st.session_state:
    st.session_state.radio_despacho = "Registro"
if 'auth' not in st.session_state: 
    st.session_state['auth'] = False

# --- AUTENTICACIÓN ---
if not st.session_state['auth']:
    st.title("🔐 Acceso Empresarial")
    u = st.text_input("Usuario")
    p = st.text_input("Contraseña", type="password")
    if st.button("Iniciar Sesión"):
        res = c.execute("SELECT rol FROM usuarios WHERE usuario=? AND clave=?", (u, p)).fetchone()
        if res:
            st.session_state.update({'auth': True, 'user': u, 'rol': res[0]})
            registrar_log("Inicio de Sesión")
            st.rerun()
        else: st.error("Credenciales incorrectas")
    st.stop()

rol_actual = st.session_state['rol']
user_active = st.session_state['user']

# --- MENÚ LATERAL ---
st.sidebar.title(f"👤 {user_active}")
menu = st.sidebar.selectbox("Menú Principal", ["🧺 Inventario Equipos", "👥 Clientes y Despacho", "⏱️ Control de Tiempos", "🚚 Logística Bodega", "📊 Reporte Admin", "⚙️ Configuración"])

if st.sidebar.button("Cerrar Sesión"):
    st.session_state['auth'] = False
    st.rerun()

# --- MÓDULO 0: INVENTARIO DE LAVADORAS ---
if menu == "🧺 Inventario Equipos":
    st.title("🧺 Gestión de Lavadoras")
    
    def guardar_lavadora():
        s = st.session_state.serie_input
        m = st.session_state.modelo_input
        if s and m:
            c.execute("INSERT INTO lavadoras (serie, modelo, estado) VALUES (?,?,'Disponible')", (s, m))
            conn.commit()
            st.toast(f"✅ Lavadora {s} registrada")
        else: st.warning("Complete los campos")

    with st.form("reg_lavadora", clear_on_submit=True):
        col1, col2 = st.columns(2)
        col1.text_input("Número de Serie", key="serie_input")
        col2.text_input("Modelo / Marca", key="modelo_input")
        st.form_submit_button("Registrar Lavadora", on_click=guardar_lavadora)
    
    df_lavs = pd.read_sql_query("SELECT serie, modelo, estado FROM lavadoras", conn)
    st.dataframe(df_lavs, use_container_width=True)

# --- MÓDULO 1: CLIENTES Y DESPACHO ---
elif menu == "👥 Clientes y Despacho":
    st.title("👥 Gestión de Clientes y Salida")

    opcion = st.radio("Seleccione Acción:", ["Registro", "Despacho"], 
                      key="radio_despacho",
                      horizontal=True)

    if opcion == "Registro":
        def procesar_cliente():
            nom = st.session_state.c_nom
            tel = st.session_state.c_tel
            gps = st.session_state.c_gps
            if nom and tel:
                lat, lon = 0.0, 0.0
                coords = re.findall(r"([-+]?\d*\.\d+|\d+)", gps)
                if len(coords)>=2: lat, lon = float(coords[0]), float(coords[1])
                c.execute("INSERT INTO clientes (nombre, tel, lat, lon, notas, fecha_registro) VALUES (?,?,?,?,?,?)",
                         (nom, tel, lat, lon, st.session_state.c_nota, datetime.now()))
                conn.commit()
                
                st.session_state.radio_despacho = "Despacho"
                st.toast(f"✅ Cliente {nom} registrado.")
                time.sleep(0.5)
                st.rerun()
            else: st.error("Nombre y Teléfono requeridos")

        with st.form("reg_cli", clear_on_submit=True):
            st.subheader("➕ Registro Nuevo Cliente")
            st.text_input("Nombre Completo", key="c_nom")
            st.text_input("WhatsApp (Ej: 58412...)", key="c_tel")
            st.text_input("Link Ubicación WhatsApp", key="c_gps")
            st.text_area("Notas de Dirección", key="c_nota")
            st.form_submit_button("Guardar Cliente y Continuar", on_click=procesar_cliente)

    else:
        st.subheader("🚀 Despacho de Equipos")
        if st.button("⬅️ Volver a Registro"):
            st.session_state.radio_despacho = "Registro"
            st.rerun()

        df_c = pd.read_sql_query("SELECT id, nombre, tel FROM clientes ORDER BY id DESC", conn)
        df_l = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Disponible'", conn)
        df_r = pd.read_sql_query("SELECT usuario FROM usuarios WHERE rol='Repartidor'", conn)

        if not df_c.empty and not df_l.empty:
            with st.form("form_despacho", clear_on_submit=True):
                c1, c2 = st.columns(2)
                c_sel = c1.selectbox("👤 Seleccionar Cliente", df_c['nombre'])
                l_sel = c1.selectbox("🧺 Seleccionar Lavadora", df_l['serie'])
                rep_sel = c2.selectbox("🚚 Asignar Repartidor", df_r['usuario'])
                hrs = c2.number_input("Horas de Alquiler", min_value=1, value=4)
                
                confirmar = st.form_submit_button("🚀 Confirmar y Enviar")

            if confirmar:
                row_c = df_c[df_c['nombre'] == c_sel].iloc[0]
                id_l = df_l[df_l['serie'] == l_sel]['id'].values[0]
                f_ini = datetime.now()
                f_fin = f_ini + timedelta(hours=hrs)

                # Guardar en DB
                c.execute("INSERT INTO alquileres_activos (id_cliente, id_lavadora, inicio, fin, repartidor_asig) VALUES (?,?,?,?,?)",
                         (row_c['id'], id_l, f_ini, f_fin, rep_sel))
                c.execute("UPDATE lavadoras SET estado='En Camino' WHERE id=?", (id_l,))
                conn.commit()

                # Preparar WhatsApp
                msg = f"✅ *¡Hola, {c_sel.upper()}!* \n\nTu lavadora ya salió. Repartidor: *{rep_sel.upper()}*."
                url_wa = f"https://wa.me/{row_c['tel']}?text={msg.replace(' ', '%20')}"
                
                st.success("Despacho registrado con éxito.")
                st.link_button("📲 Abrir WhatsApp", url_wa)
                
                # Botón para limpiar pantalla y seguir
                if st.button("Siguiente Despacho"):
                    st.rerun()
        else:
            st.warning("No hay clientes registrados o lavadoras disponibles.")

# --- MÓDULO 2: CONTROL Y COBRO ---
elif menu == "⏱️ Control de Tiempos":
    st.title("⏱️ Monitor de Alquileres")
    query = '''SELECT a.id, c.nombre, c.tel, l.serie, l.id as id_lav, a.fin, a.horas_extras, a.avisado, a.repartidor_asig 
               FROM alquileres_activos a JOIN clientes c ON a.id_cliente = c.id JOIN lavadoras l ON a.id_lavadora = l.id'''
    activos = pd.read_sql_query(query, conn)

    if activos.empty:
        st.info("No hay alquileres activos.")
    else:
        for _, row in activos.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([2,2,1.5])
                f_fin = datetime.strptime(row['fin'], "%Y-%m-%d %H:%M:%S.%f")
                restante = int((f_fin - datetime.now()).total_seconds() / 60)
                c1.write(f"### {row['nombre']}")
                if restante > 0: c2.success(f"⏳ {restante} min restantes")
                else: c2.error(f"⚠️ Retraso de {abs(restante)} min")
                
                with c3:
                    if st.button("🏁 Cobrar", key=f"cob_{row['id']}"):
                        monto = st.number_input("Total $", key=f"v_{row['id']}")
                        if st.button("Confirmar Pago", key=f"f_{row['id']}"):
                            c.execute("INSERT INTO historial_alquileres (id_cliente, id_lavadora, fecha, monto, usuario_cobro) VALUES (?,?,?,?,?)",
                                     (row['id'], row['id_lav'], datetime.now(), monto, user_active))
                            c.execute("UPDATE lavadoras SET estado='Retornando' WHERE id=?", (row['id_lav'],))
                            c.execute("DELETE FROM alquileres_activos WHERE id=?", (row['id'],))
                            conn.commit()
                            st.rerun()

# --- MÓDULO 3: LOGÍSTICA BODEGA ---
elif menu == "🚚 Logística Bodega":
    st.title("📥 Recepción en Bodega")
    df_ret = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Retornando'", conn)
    if df_ret.empty:
        st.info("No hay equipos pendientes por retornar.")
    for _, l in df_ret.iterrows():
        if st.button(f"📥 Confirmar Recepción: {l['serie']}"):
            c.execute("UPDATE lavadoras SET estado='Disponible' WHERE id=?", (l['id'],))
            conn.commit()
            st.rerun()

# --- MÓDULO 4: REPORTES ---
elif menu == "📊 Reporte Admin":
    if rol_actual != "Admin": st.error("Acceso denegado"); st.stop()
    st.title("📊 Resumen de Ventas")
    df_h = pd.read_sql_query("SELECT * FROM historial_alquileres", conn)
    if not df_h.empty:
        st.metric("Total Recaudado", f"${df_h['monto'].sum():,.2f}")
        st.dataframe(df_h, use_container_width=True)
    else:
        st.info("Aún no hay registros de ventas.")

# --- MÓDULO 5: CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    if rol_actual != "Admin": st.error("Acceso denegado"); st.stop()
    st.warning("Zona de Peligro")
    confirm = st.text_input("Escribe 'BORRAR' para resetear la base de datos")
    if st.button("EJECUTAR RESET TOTAL") and confirm == "BORRAR":
        c.execute("DELETE FROM clientes")
        c.execute("DELETE FROM alquileres_activos")
        c.execute("DELETE FROM lavadoras")
        c.execute("DELETE FROM historial_alquileres")
        conn.commit()
        st.success("Base de datos reseteada.")
        st.rerun()
