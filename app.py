import streamlit as st
import psycopg2
import os
import pandas as pd
import streamlit.components.v1 as components
from dotenv import load_dotenv
from datetime import date

load_dotenv()
st.set_page_config(page_title="Brider ERP Mobile", page_icon="🔋", layout="centered")

# --- ESTILOS ---
st.markdown("""
    <style>
        html, body, [class*="css"] {
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }
        .stButton>button {
            border-radius: 8px !important;
            padding: 0.6rem 1rem !important;
            font-weight: 600 !important;
        }
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        .confirm-box {
            background-color: #f8fafc;
            border-radius: 16px;
            padding: 2rem;
            max-width: 500px;
            margin: 2rem auto;
            text-align: center;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        .confirm-box h2 {
            color: #1e293b;
            margin-bottom: 1rem;
        }
        .confirm-box .total {
            font-size: 2.5rem;
            font-weight: 700;
            color: #0f172a;
            margin: 1rem 0;
        }
        .confirm-box .detail {
            color: #475569;
            font-size: 1rem;
            margin: 0.5rem 0;
        }
        .confirm-box .buttons {
            display: flex;
            gap: 1rem;
            justify-content: center;
            margin-top: 1.5rem;
        }
    </style>
""", unsafe_allow_html=True)

# --- INICIALIZACIÓN DE SESIÓN ---
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False
if 'usuario_actual' not in st.session_state:
    st.session_state.usuario_actual = None
if 'nombre_completo' not in st.session_state:
    st.session_state.nombre_completo = None
if 'rol_actual' not in st.session_state:
    st.session_state.rol_actual = None
if 'carrito' not in st.session_state:
    st.session_state.carrito = []
if 'id_venta_generado' not in st.session_state:
    st.session_state.id_venta_generado = None
if 'ultima_venta' not in st.session_state:
    st.session_state.ultima_venta = None
if 'vista_confirmacion' not in st.session_state:
    st.session_state.vista_confirmacion = False   # True = mostrar pantalla de confirmación
if 'fecha_venta' not in st.session_state:
    st.session_state.fecha_venta = date.today()
if 'cliente_seleccionado' not in st.session_state:
    st.session_state.cliente_seleccionado = None
if 'tipo_pago' not in st.session_state:
    st.session_state.tipo_pago = "Contado"
if 'monto_contado' not in st.session_state:
    st.session_state.monto_contado = 0.0
if 'monto_credito' not in st.session_state:
    st.session_state.monto_credito = 0.0
if 'medio_cash' not in st.session_state:
    st.session_state.medio_cash = "Ninguno"
if 'total_factura' not in st.session_state:
    st.session_state.total_factura = 0.0

# --- FUNCIONES DE BASE DE DATOS (con caché) ---
@st.cache_resource
def init_connection():
    try:
        db_url = st.secrets["DATABASE_URL"]
    except Exception:
        db_url = os.getenv("DATABASE_URL")
    return psycopg2.connect(db_url, sslmode="require")

@st.cache_data(ttl=300)
def obtener_clientes():
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ruc, razon_social FROM clientes ORDER BY razon_social;")
    filas = cursor.fetchall()
    cursor.close()
    return [f"{fila[0]} | {fila[1]}" for fila in filas]

@st.cache_data(ttl=300)
def obtener_catalogo_completo():
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id_bateria, modelo, tipo, precio_con_igv, stock_actual FROM catalogo_baterias;")
    filas = cursor.fetchall()
    cursor.close()
    return filas

def verificar_login(user, password):
    conn = init_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nombre_apellido, rol FROM usuarios WHERE username = %s AND password_plana = %s;", (user, password))
    resultado = cursor.fetchone()
    cursor.close()
    return {"nombre": resultado[0], "rol": resultado[1]} if resultado else None

def guardar_bateria_nueva(modelo, tipo, precio, stock):
    conn = init_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO catalogo_baterias (modelo, tipo, precio_con_igv, stock_actual) VALUES (%s, %s, %s, %s);", (modelo, tipo, precio, stock))
        conn.commit()
        st.cache_data.clear()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        cursor.close()

def registrar_venta_corporativa_multi(ruc, fecha, tipo_pago, total_general, m_contado, m_credito, vendedor, medio_cash, carrito):
    conn = init_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO ventas_cabecera (
                ruc_cliente, fecha_venta, tipo_pago, monto_total, 
                vendedor, estado_auditoria, monto_contado, monto_credito, medio_pago_cash
            )
            VALUES (%s, %s, %s, %s, %s, 'Pendiente', %s, %s, %s) RETURNING id_venta;
        """, (ruc, fecha, tipo_pago, total_general, vendedor, m_contado, m_credito, medio_cash))
        id_venta = cursor.fetchone()[0]

        for item in carrito:
            cursor.execute("""
                INSERT INTO ventas_detalle (id_venta, id_bateria, cantidad, descuento_porcentaje, subtotal, igv, total_pagar)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, (id_venta, item["id"], item["cantidad"], item["desc_pct"], item["subtotal"], item["igv"], item["total"]))
            cursor.execute("UPDATE catalogo_baterias SET stock_actual = stock_actual - %s WHERE id_bateria = %s;", (item["cantidad"], item["id"]))

        conn.commit()
        st.cache_data.clear()
        return id_venta
    except Exception as e:
        conn.rollback()
        st.error(f"Error crítico en transacción: {e}")
        return None
    finally:
        cursor.close()

# =========================================================================
# LOGIN
# =========================================================================
if not st.session_state.autenticado:
    st.markdown("<h3 style='text-align: center; font-weight: 700;'>🔋 GRUPO BRIDER</h3>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Gestión Comercial Móvil</p>", unsafe_allow_html=True)
    with st.form("login_mobile"):
        input_user = st.text_input("Usuario")
        input_pass = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Ingresar al Sistema", use_container_width=True):
            user_data = verificar_login(input_user.strip(), input_pass.strip())
            if user_data:
                st.session_state.autenticado = True
                st.session_state.usuario_actual = input_user
                st.session_state.nombre_completo = user_data["nombre"]
                st.session_state.rol_actual = user_data["rol"]
                st.rerun()
            else:
                st.error("Credenciales de acceso inválidas")
    st.stop()

# =========================================================================
# VISTA DE CONFIRMACIÓN (reemplaza completamente la vista principal)
# =========================================================================
if st.session_state.vista_confirmacion:
    st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
    st.markdown("<h2>📋 Confirmar Venta</h2>", unsafe_allow_html=True)
    
    # Resumen de la venta
    total = st.session_state.total_factura
    cliente = st.session_state.cliente_seleccionado.split(" | ")[1] if st.session_state.cliente_seleccionado else "No seleccionado"
    tipo_pago = st.session_state.tipo_pago
    monto_contado = st.session_state.monto_contado
    monto_credito = st.session_state.monto_credito
    medio_cash = st.session_state.medio_cash
    fecha = st.session_state.fecha_venta.strftime("%d/%m/%Y")
    
    st.markdown(f"""
        <div class="confirm-box">
            <p class="detail"><strong>Cliente:</strong> {cliente}</p>
            <p class="detail"><strong>Fecha:</strong> {fecha}</p>
            <p class="detail"><strong>Método de pago:</strong> {tipo_pago}</p>
            <p class="detail"><strong>Monto contado:</strong> S/. {monto_contado:.2f}</p>
            <p class="detail"><strong>Monto crédito:</strong> S/. {monto_credito:.2f}</p>
            <p class="detail"><strong>Canal cash:</strong> {medio_cash}</p>
            <div class="total">S/. {total:.2f}</div>
            <p style="color: #64748b; font-size: 0.9rem;">¿Confirmar el registro de esta venta?</p>
            <div class="buttons">
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Confirmar", use_container_width=True, key="confirm_btn"):
            with st.spinner("Registrando venta..."):
                ruc_cliente = st.session_state.cliente_seleccionado.split(" | ")[0]
                id_gen = registrar_venta_corporativa_multi(
                    ruc_cliente,
                    st.session_state.fecha_venta,
                    st.session_state.tipo_pago,
                    st.session_state.total_factura,
                    st.session_state.monto_contado,
                    st.session_state.monto_credito,
                    st.session_state.nombre_completo,
                    st.session_state.medio_cash,
                    st.session_state.carrito
                )
                if id_gen:
                    st.session_state.ultima_venta = {
                        "id": id_gen,
                        "cliente": st.session_state.cliente_seleccionado.split(" | ")[1],
                        "tipo_pago": st.session_state.tipo_pago,
                        "monto_contado": st.session_state.monto_contado,
                        "monto_credito": st.session_state.monto_credito,
                        "medio_pago_cash": st.session_state.medio_cash,
                        "total": st.session_state.total_factura
                    }
                    st.session_state.carrito = []
                    st.session_state.id_venta_generado = id_gen
                    st.session_state.vista_confirmacion = False
                    st.toast("✅ Venta registrada exitosamente", icon="🎉")
                    st.rerun()
                else:
                    st.error("Error al registrar la venta. Intenta nuevamente.")
                    st.session_state.vista_confirmacion = False
                    st.rerun()
    with col2:
        if st.button("❌ Cancelar", use_container_width=True, key="cancel_btn"):
            st.session_state.vista_confirmacion = False
            st.rerun()
    
    st.markdown("</div></div></div>", unsafe_allow_html=True)
    st.stop()

# =========================================================================
# CONTENIDO PRINCIPAL (solo si NO estamos en confirmación)
# =========================================================================
st.markdown(f"<p style='text-align: right; font-size: 0.85rem; color: #666;'>👤 {st.session_state.nombre_completo} ({st.session_state.rol_actual})</p>", unsafe_allow_html=True)
st.title("🛒 Terminal de Ventas")

lista_clientes = obtener_clientes()
datos_catalogo = obtener_catalogo_completo()

opciones_baterias = [f"{d[1]} - S/.{d[3]} (Stock: {d[4]})" for d in datos_catalogo]
diccionario_baterias = {f"{d[1]} - S/.{d[3]} (Stock: {d[4]})": {"id": d[0], "modelo": d[1], "precio": d[3], "stock": d[4]} for d in datos_catalogo}

# --- PANEL ADMIN ---
if st.session_state.rol_actual == "Administrador":
    with st.expander("🛠️ Panel Admin: Añadir Batería al Catálogo"):
        with st.form("add_bateria"):
            n_modelo = st.text_input("Modelo de Batería (Ej: 15 Placas)")
            n_tipo = st.selectbox("Tipo de Vehículo", ["Auto", "Moto", "Camión"])
            n_precio = st.number_input("Precio Venta (Con IGV Incluido)", min_value=0.0, format="%.2f")
            n_stock = st.number_input("Stock Inicial", min_value=0, step=1)
            if st.form_submit_button("Guardar en Catálogo"):
                if n_modelo and guardar_bateria_nueva(n_modelo, n_tipo, n_precio, n_stock):
                    st.toast("✅ Batería agregada exitosamente", icon="🎉")
                    st.rerun()
                else:
                    st.error("Error al registrar producto.")

# --- CLIENTE ---
cliente_sel = st.selectbox("1. Seleccione el Cliente", lista_clientes)
st.session_state.cliente_seleccionado = cliente_sel
st.markdown("---")

# --- CARRITO ---
st.subheader("2. Añadir Baterías")
if not opciones_baterias:
    st.warning("No hay baterías en el catálogo. Contacte al administrador.")
    st.stop()

bateria_sel = st.selectbox("Modelo de Batería", opciones_baterias)
bat_info = diccionario_baterias[bateria_sel]

cant_input = st.number_input("Cantidad", min_value=1, step=1, value=1)
desc_input = st.selectbox("Descuento Aplicable", ["10%", "15%", "20%", "0%"], index=0)

cant_en_carrito = sum(item["cantidad"] for item in st.session_state.carrito if item["id"] == bat_info["id"])
stock_real_disponible = bat_info["stock"] - cant_en_carrito

if st.button("🛒 Añadir al Carrito", use_container_width=True):
    if cant_input > stock_real_disponible:
        st.error(f"Stock insuficiente. Disponible neto en almacén: {stock_real_disponible} unidades.")
    else:
        p_unitario = float(bat_info["precio"])
        pct = float(desc_input.replace("%", "")) / 100
        t_bruto = p_unitario * cant_input
        t_desc = t_bruto * pct
        t_pagar_item = t_bruto - t_desc
        sub_item = t_pagar_item / 1.18
        igv_item = t_pagar_item - sub_item
        
        st.session_state.carrito.append({
            "id": bat_info["id"],
            "modelo": bat_info["modelo"],
            "cantidad": cant_input,
            "desc_pct": pct * 100,
            "subtotal": sub_item,
            "igv": igv_item,
            "total": t_pagar_item
        })
        st.toast(f"✅ {bat_info['modelo']} añadido al carrito", icon="🛒")
        st.rerun()

# --- DETALLE DEL CARRITO ---
if st.session_state.carrito:
    st.markdown("### **Detalle del Carrito**")
    df_carrito = pd.DataFrame(st.session_state.carrito)
    st.dataframe(df_carrito[["modelo", "cantidad", "total"]], hide_index=True, use_container_width=True)
    
    if st.button("🗑️ Vaciar Carrito", type="secondary"):
        st.session_state.carrito = []
        st.rerun()
        
    st.markdown("---")

    # --- PARÁMETROS DE PAGO Y FECHA ---
    st.subheader("3. Parámetros de Pago")
    total_factura = sum(item["total"] for item in st.session_state.carrito)
    st.metric(label="TOTAL GENERAL A COBRAR", value=f"S/. {total_factura:.2f}")

    fecha_venta = st.date_input("Fecha de la venta", value=st.session_state.fecha_venta)
    st.session_state.fecha_venta = fecha_venta

    tipo_pago = st.selectbox("Método de Pago", ["Contado", "Crédito", "Mixto"])
    st.session_state.tipo_pago = tipo_pago
    st.session_state.total_factura = total_factura

    monto_contado = 0.0
    monto_credito = 0.0
    medio_cash_sel = "Ninguno"

    if tipo_pago == "Contado":
        monto_contado = total_factura
        medio_cash_sel = st.selectbox("Canal de Recepción Cash", ["Efectivo", "Yape", "Plin", "Visa", "Mastercard", "Transferencia"])
    elif tipo_pago == "Crédito":
        monto_credito = total_factura
    elif tipo_pago == "Mixto":
        monto_contado = st.number_input("Monto pagado al Contado (S/.)", min_value=0.0, max_value=float(total_factura), step=10.0)
        monto_credito = float(total_factura) - monto_contado
        st.warning(f"Saldo restante a Crédito: S/. {monto_credito:.2f}")
        if monto_contado > 0:
            medio_cash_sel = st.selectbox("Canal de Recepción Cash (Parte Líquida)", ["Efectivo", "Yape", "Plin", "Visa", "Mastercard", "Transferencia"])

    st.session_state.monto_contado = monto_contado
    st.session_state.monto_credito = monto_credito
    st.session_state.medio_cash = medio_cash_sel

    st.markdown("---")

    # --- BOTÓN REGISTRAR VENTA (cambia a vista de confirmación) ---
    if st.button("🚀 Registrar Venta", type="primary", use_container_width=True):
        st.session_state.vista_confirmacion = True
        st.rerun()

# --- VOUCHER EMITIDO ---
if st.session_state.id_venta_generado is not None and st.session_state.ultima_venta:
    v = st.session_state.ultima_venta
    st.success("🎉 ¡Operación Registrada Exitosamente!")
    
    ticket_movil = f"""*BRIDER E.I.R.L. - COMPROBANTE*
----------------------------------------
*Doc Nro:* TR-{v['id']:05d}
*Fecha:* {st.session_state.fecha_venta.strftime('%d/%m/%Y')}
*Vendedor:* {st.session_state.nombre_completo}
*Cliente:* {v['cliente']}
----------------------------------------
*Condición:* {v['tipo_pago']}
*Canal Cash:* {v['medio_pago_cash']}
*Cobrado Cash:* S/. {v['monto_contado']:.2f}
*Por Cobrar:* S/. {v['monto_credito']:.2f}
----------------------------------------
*TOTAL PROCESADO: S/. {v['total']:.2f}*
----------------------------------------
¡Gracias por confiar en Grupo Brider!
"""
    st.code(ticket_movil, language="text")
    ticket_js = ticket_movil.replace("\n", "\\n")
    
    html_share = f"""
    <button id="nativeShareBtn" style="
        width: 100%;
        background-color: #1E293B;
        color: white;
        border: none;
        padding: 12px 20px;
        font-size: 16px;
        font-weight: 600;
        border-radius: 8px;
        cursor: pointer;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    ">
        🔗 Compartir Comprobante
    </button>
    <script>
        const btn = document.getElementById('nativeShareBtn');
        btn.addEventListener('click', async () => {{
            const shareData = {{
                title: 'Comprobante Brider',
                text: `{ticket_js}`
            }};
            try {{
                if (navigator.share) {{
                    await navigator.share(shareData);
                }} else {{
                    navigator.clipboard.writeText(shareData.text);
                    alert('Texto de la factura copiado al portapapeles.');
                }}
            }} catch (err) {{
                console.log('Cancelado:', err);
            }}
        }});
    </script>
    """
    components.html(html_share, height=55)
    
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Nueva Transacción 🔁", use_container_width=True):
        st.session_state.id_venta_generado = None
        st.session_state.ultima_venta = None
        st.rerun()

# --- CIERRE DE SESIÓN ---
st.markdown("<br><br>", unsafe_allow_html=True)
if st.button("🔒 Cerrar Sesión del Sistema", type="secondary", use_container_width=True):
    for key in ['autenticado', 'usuario_actual', 'nombre_completo', 'rol_actual', 'carrito', 
                'id_venta_generado', 'ultima_venta', 'vista_confirmacion']:
        if key in st.session_state:
            if key == 'usuario_actual':
                st.session_state[key] = None
            elif key in ['autenticado', 'vista_confirmacion']:
                st.session_state[key] = False
            elif key == 'carrito':
                st.session_state[key] = []
            else:
                st.session_state[key] = None
    st.rerun()
