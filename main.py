import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import re
from contextlib import contextmanager

# --- CONFIGURACIÓN ESTÉTICA ---
st.set_page_config(page_title="Lavandería Master Pro v5.0", layout="wide", page_icon="🧺")

# --- GESTIÓN ROBUSTA DE BASE DE DATOS ---
DB_NAME = 'sistema_lavanderia_v4.db'

@contextmanager
def db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def inicializar_db():
    with db_connection() as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS usuarios (usuario TEXT PRIMARY KEY, clave TEXT, rol TEXT)')
        c.execute('''CREATE TABLE IF NOT EXISTS clientes 
                     (id INTEGER PRIMARY KEY, nombre TEXT, tel TEXT, lat REAL, lon REAL, notas TEXT, fecha_registro DATETIME)''')
        c.execute('CREATE TABLE IF NOT EXISTS lavadoras (id INTEGER PRIMARY KEY, serie TEXT, modelo TEXT, estado TEXT)')
        c.execute('''CREATE TABLE IF NOT EXISTS alquileres_activos 
                     (id INTEGER PRIMARY KEY, id_cliente INTEGER, id_lavadora INTEGER, inicio DATETIME, fin DATETIME)''')
        c.execute('''CREATE TABLE IF NOT EXISTS historial_alquileres 
                     (id INTEGER PRIMARY KEY, id_cliente INTEGER, id_lavadora INTEGER, fecha DATETIME, 
                      monto REAL, usuario_cobro TEXT)''')
        c.execute("INSERT OR IGNORE INTO usuarios VALUES ('admin', 'admin123', 'Admin'), ('cajera', 'caja123', 'Cajera')")
        conn.commit()

inicializar_db()

# --- ESTADOS DE SESIÓN ---
if 'paso_despacho' not in st.session_state: st.session_state.paso_despacho = 0
if 'auth' not in st.session_state: st.session_state['auth'] = False

# --- AUTENTICACIÓN ---
if not st.session_state['auth']:
    st.title("🔐 Acceso Empresarial")
    with st.form("login_form"):
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Iniciar Sesión"):
            with db_connection() as conn:
                res = conn.execute("SELECT rol FROM usuarios WHERE usuario=? AND clave=?", (u, p)).fetchone()
                if res:
                    st.session_state.update({'auth': True, 'user': u, 'rol': res['rol']})
                    st.rerun()
                else: st.error("Credenciales incorrectas")
    st.stop()

# --- NAVEGACIÓN LATERAL ---
st.sidebar.title(f"👤 {st.session_state['user']}")
menu = st.sidebar.selectbox("Menú Principal", ["🧺 Equipos", "👥 Clientes/Despacho", "⏱️ Monitor", "🚚 Recepción", "📊 Reportes"])

if st.sidebar.button("Cerrar Sesión"):
    st.session_state['auth'] = False
    st.rerun()

# --- MÓDULO 0: INVENTARIO ---
if menu == "🧺 Equipos":
    st.title("🧺 Gestión de Inventario")
    with st.form("reg_lav", clear_on_submit=True):
        col1, col2 = st.columns(2)
        s = col1.text_input("Número de Serie")
        m = col2.text_input("Modelo / Marca")
        if st.form_submit_button("Registrar Lavadora"):
            if s and m:
                with db_connection() as conn:
                    conn.execute("INSERT INTO lavadoras (serie, modelo, estado) VALUES (?,?,'Disponible')", (s, m))
                    conn.commit()
                st.success(f"Lavadora {s} registrada correctamente.")
            else: st.warning("Complete todos los campos.")
    
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT serie, modelo, estado FROM lavadoras", conn)
        st.dataframe(df, use_container_width=True)

# --- MÓDULO 1: CLIENTES Y DESPACHO ---
elif menu == "👥 Clientes/Despacho":
    st.title("👥 Clientes y Salidas")
    opcion = st.radio("Acción:", ["Registro", "Despacho"], index=st.session_state.paso_despacho, horizontal=True)
    st.session_state.paso_despacho = 0 if opcion == "Registro" else 1

    if st.session_state.paso_despacho == 0:
        with st.form("cli_form", clear_on_submit=True):
            st.subheader("📝 Nuevo Registro")
            nom = st.text_input("Nombre Completo")
            tel = st.text_input("WhatsApp (Ej: 584121234567)")
            gps = st.text_input("Link Ubicación (Google Maps)")
            notas = st.text_area("Notas de Dirección")
            if st.form_submit_button("Guardar y Continuar"):
                if nom and tel:
                    coords = re.findall(r"([-+]?\d+\.\d+)", gps)
                    lat = float(coords[0]) if len(coords) >= 2 else 0.0
                    lon = float(coords[1]) if len(coords) >= 2 else 0.0
                    with db_connection() as conn:
                        conn.execute("INSERT INTO clientes (nombre, tel, lat, lon, notas, fecha_registro) VALUES (?,?,?,?,?,?)",
                                     (nom, tel, lat, lon, notas, datetime.now()))
                        conn.commit()
                    st.session_state.paso_despacho = 1
                    st.rerun()
                else: st.error("Nombre y Teléfono requeridos.")

    else:
        st.subheader("🚀 Nueva Salida de Equipo")
        with db_connection() as conn:
            clientes_df = pd.read_sql_query("SELECT id, nombre, tel FROM clientes ORDER BY id DESC", conn)
            lavadoras_df = pd.read_sql_query("SELECT id, serie FROM lavadoras WHERE estado='Disponible'", conn)
        
        if not clientes_df.empty and not lavadoras_df.empty:
            with st.form("despacho_form"):
                col_a, col_b = st.columns(2)
                c_sel = col_a.selectbox("Seleccionar Cliente", clientes_df['nombre'])
                l_sel = col_b.selectbox("Seleccionar Lavadora", lavadoras_df['serie'])
                hrs = st.number_input("Horas de alquiler", 1, 72, 4)
                
                cliente_data = clientes_df[clientes_df['nombre'] == c_sel].iloc[0]
                
                if st.form_submit_button("Confirmar Salida"):
                    id_c = cliente_data['id']
                    id_l = lavadoras_df[lavadoras_df['serie'] == l_sel]['id'].values[0]
                    f_fin = datetime.now() + timedelta(hours=hrs)
                    
                    with db_connection() as conn:
                        conn.execute("INSERT INTO alquileres_activos (id_cliente, id_lavadora, inicio, fin) VALUES (?,?,?,?)",
                                     (id_c, id_l, datetime.now(), f_fin))
                        conn.execute("UPDATE lavadoras SET estado='En Uso' WHERE id=?", (id_l,))
                        conn.commit()
                    
                    st.session_state.last_dispatch = {
                        "nombre": c_sel.upper(),
                        "tel": cliente_data['tel'],
                        "equipo": l_sel,
                        "fin": f_fin.strftime("%H:%M"),
                        "horas": hrs
                    }
                    st.rerun()
            
            if 'last_dispatch' in st.session_state:
                disp = st.session_state.last_dispatch
                msg = (f"✅ *LAVANDERÍA LOS AUTÉNTICOS EXPRESS*\n\n"
                       f"Hola *{disp['nombre']}*, tu equipo *{disp['equipo']}* ha sido despachado.\n"
                       f"⏰ Tiempo: *{disp['horas']} horas*.\n"
                       f"🔔 Retiro estimado: *{disp['fin']}*.\n\n"
                       f"¡Gracias por su preferencia!")
                
                clean_tel = ''.join(filter(str.isdigit, disp['tel']))
                url_wa = f"https://wa.me/{clean_tel}?text={re.sub(r'\s', '%20', msg)}"
                
                st.divider()
                st.link_button(f"📲 Enviar WhatsApp a {disp['nombre']}", url_wa, type="primary", use_container_width=True)
                if st.button("Limpiar y Nuevo Despacho"):
                    del st.session_state.last_dispatch
                    st.rerun()
        else: st.warning("No hay clientes registrados o lavadoras disponibles.")

# --- MÓDULO 2: MONITOR ---
elif menu == "⏱️ Monitor":
    st.title("⏱️ Control de Alquileres Activos")
    query = '''SELECT a.id, c.nombre, l.serie, l.id as lid, a.fin FROM alquileres_activos a 
               JOIN clientes c ON a.id_cliente = c.id JOIN lavadoras l ON a.id_lavadora = l.id'''
    with db_connection() as conn:
        activos = pd.read_sql_query(query, conn)

    if activos.empty:
        st.info("No hay equipos en alquiler actualmente.")
    else:
        for _, row in activos.iterrows():
            with st.container(border=True):
                col1, col2, col3 = st.columns([2,2,1])
                col1.write(f"### {row['nombre']}")
                col1.write(f"Lavadora: **{row['serie']}**")
                
                fin_dt = pd.to_datetime(row['fin'])
                resta = (fin_dt - datetime.now()).total_seconds() / 60
                if resta > 0: col2.success(f"⏳ {int(resta)} min restantes")
                else: col2.error(f"⚠️ Retraso: {abs(int(resta))} min")

                with col3.popover("🏁 Finalizar"):
                    with st.form(f"f_{row['id']}"):
                        monto = st.number_input("Monto Cobrado $", min_value=0.0, key=f"m_{row['id']}")
                        if st.form_submit_button("Confirmar Cobro"):
                            with db_connection() as conn:
                                conn.execute("INSERT INTO historial_alquileres (id_cliente, id_lavadora, fecha, monto, usuario_cobro) VALUES (?,?,?,?,?)",
                                             (row['id'], row['lid'], datetime.now(), monto, st.session_state['user']))
                                conn.execute("UPDATE lavadoras SET estado='Retornando' WHERE id=?", (row['lid'],))
                                conn.execute("DELETE FROM alquileres_activos WHERE id=?", (row['id'],))
                                conn.commit()
                            st.rerun()

# --- MÓDULO 3: RECEPCIÓN ---
elif menu == "🚚 Recepción":
    st.title("📥 Reingreso a Bodega")
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT id, serie, modelo FROM lavadoras WHERE estado='Retornando'", conn)
    
    if df.empty:
        st.info("No hay equipos pendientes de reingreso.")
    else:
        for _, l in df.iterrows():
            if st.button(f"📥 Confirmar Entrada: {l['serie']} ({l['modelo']})", key=f"rec_{l['id']}", use_container_width=True):
                with db_connection() as conn:
                    conn.execute("UPDATE lavadoras SET estado='Disponible' WHERE id=?", (l['id'],))
                    conn.commit()
                st.rerun()

# --- MÓDULO 4: REPORTES ---
elif menu == "📊 Reportes":
    if st.session_state['rol'] != "Admin": 
        st.error("Acceso restringido a Administradores.")
        st.stop()
        
    st.title("📊 Reporte de Ventas")
    
    with db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM historial_alquileres", conn)
    
    st.metric("Recaudación Total", f"${df['monto'].sum():,.2f}")
    st.dataframe(df, use_container_width=True)

    # --- SECCIÓN DE PELIGRO (BORRADO DE DATOS) ---
    st.divider()
    with st.expander("⚠️ ZONA DE PELIGRO - Configuración Avanzada"):
        st.warning("Las siguientes acciones son irreversibles. Proceda con precaución.")
        
        # Checkbox de seguridad adicional
        confirmacion = st.checkbox("Entiendo que borrar los datos eliminará todo el historial, clientes y equipos.")
        
        if st.button("🔥 ELIMINAR TODOS LOS DATOS DEL SISTEMA", type="secondary", disabled=not confirmacion):
            try:
                with db_connection() as conn:
                    c = conn.cursor()
                    # Borramos contenido de todas las tablas excepto 'usuarios'
                    c.execute("DELETE FROM historial_alquileres")
                    c.execute("DELETE FROM alquileres_activos")
                    c.execute("DELETE FROM lavadoras")
                    c.execute("DELETE FROM clientes")
                    conn.commit()
                
                st.toast("Base de datos limpiada con éxito", icon="🗑️")
                st.success("Todos los registros han sido eliminados. El sistema está vacío.")
                time.sleep(2)
                st.rerun()
            except Exception as e:
                st.error(f"Error al intentar borrar: {e}")
