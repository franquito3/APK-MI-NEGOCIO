"""
Mi Negocio - Flet + Supabase (Generación de PDF y Ticket Digital)
"""
import asyncio
import os
import tempfile
from datetime import date

import flet as ft
from supabase import AsyncClient, acreate_client

# ====================== CREDENCIALES SUPABASE ======================
SUPABASE_URL = "https://pgzpuysruhogvhiinzor.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBnenB1eXNydWhvZ3ZoaWluem9yIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE2NjU3NDgsImV4cCI6MjEwNzI0MTc0OH0.IWBb2bNS-c7YRlB6jysqA7rC_ceGA2AQbzf_RQ0wugM"
# ===================================================================

MONEDA = "S/"
TABLAS = ("productos", "ventas_v2", "venta_items", "pagos", "gastos", "config")
VERDE = ft.Colors.TEAL_700
LIMITE_LISTA = 100


def money(x: float) -> str:
    return f"{MONEDA} {x:,.2f}"


def num(texto, defecto=None):
    try:
        return float(str(texto).replace(",", ".").strip())
    except (ValueError, AttributeError):
        return defecto


async def traer_todo(client: AsyncClient, tabla: str, columnas="*", orden="id"):
    filas, desde, paso = [], 0, 1000
    while True:
        r = (
            await client.table(tabla)
            .select(columnas)
            .order(orden, desc=True)
            .range(desde, desde + paso - 1)
            .execute()
        )
        filas.extend(r.data)
        if len(r.data) < paso:
            return filas
        desde += paso


async def main(page: ft.Page):
    page.title = "Mi Negocio"
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.TEAL)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 12
    page.bgcolor = ft.Colors.BLUE_GREY_50
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    page.add(
        ft.Container(
            expand=True,
            content=ft.Column(
                [
                    ft.ProgressRing(color=ft.Colors.TEAL_700),
                    ft.Text("Iniciando Mi Negocio...", color=ft.Colors.BLUE_GREY_700),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
            ),
        )
    )
    page.update()

    client: AsyncClient = await acreate_client(SUPABASE_URL, SUPABASE_KEY)

    # Estado de la app
    estado = {"capital": 0.0, "productos": [], "ventas": [], "pagos": [], "gastos": []}
    carga_inicial = True
    carrito_actual = []
    lock = asyncio.Lock()

    # ==================== INDICADOR DE CONEXIÓN ====================
    txt_conexion = ft.Text("Conectando...", size=12, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)
    icon_conexion = ft.Icon(ft.Icons.WIFI_FIND, size=14, color=ft.Colors.WHITE)
    badge_conexion = ft.Container(
        content=ft.Row([icon_conexion, txt_conexion], spacing=4),
        bgcolor=ft.Colors.ORANGE_700,
        padding=ft.padding.symmetric(horizontal=8, vertical=4),
        border_radius=12,
    )
    

    def set_conexion(online: bool):
        if online:
            badge_conexion.bgcolor = ft.Colors.GREEN_700
            icon_conexion.name = ft.Icons.WIFI
            txt_conexion.value = "Conectado"
        else:
            badge_conexion.bgcolor = ft.Colors.RED_700
            icon_conexion.name = ft.Icons.WIFI_OFF
            txt_conexion.value = "Sin internet"
        page.update()

    def aviso(texto, error=False):
        page.open(
            ft.SnackBar(
                ft.Text(texto, color=ft.Colors.WHITE),
                bgcolor=ft.Colors.RED_700 if error else ft.Colors.GREEN_700,
            )
        )

    def abrir_calendario(campo_destino):
        def al_seleccionar_fecha(e):
            if e.control.value:
                campo_destino.value = e.control.value.strftime("%Y-%m-%d")
                page.update()

        page.open(
            ft.DatePicker(
                first_date=date(2024, 1, 1),
                last_date=date(2030, 12, 31),
                on_change=al_seleccionar_fecha,
            )
        )

    # ==================== RESUMEN Y TARJETAS ORIGINALES ====================
    def resumen():
        v = estado["ventas"]
        vendido = round(sum(x["total"] or 0 for x in v), 2)
        cobrado = round(sum(p["monto"] or 0 for p in estado["pagos"]), 2)
        gastos = round(sum(x["monto"] or 0 for x in estado["gastos"]), 2)
        capital = estado["capital"]
        return dict(
            capital=capital,
            vendido=vendido,
            cobrado=cobrado,
            por_cobrar=round(vendido - cobrado, 2),
            gastos=gastos,
            ganancia=round(cobrado - gastos, 2),
            caja=round(capital + cobrado - gastos, 2),
        )

    def tarjeta(titulo, valor, color, grande=False):
        return ft.Card(
            color=color,
            margin=0,
            content=ft.Container(
                padding=12,
                content=ft.Column(
                    [
                        ft.Text(titulo, size=13, color=ft.Colors.WHITE70, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(valor, size=26 if grande else 20, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE, overflow=ft.TextOverflow.ELLIPSIS),
                    ],
                    spacing=2,
                ),
            ),
        )

    def skeleton_card():
        return ft.Card(
            content=ft.Container(
                padding=12,
                content=ft.Column(
                    [
                        ft.Container(width=110, height=12, bgcolor=ft.Colors.GREY_300, border_radius=6),
                        ft.Container(width=180, height=22, bgcolor=ft.Colors.GREY_200, border_radius=6),
                    ],
                    spacing=8,
                ),
            )
        )

    def skeleton_list(cantidad=3):
        return [skeleton_card() for _ in range(cantidad)]

    tarjetas = ft.Column(
        [
            ft.Row([ft.Container(skeleton_card(), expand=True)]),
            ft.Row([ft.Container(skeleton_card(), expand=True), ft.Container(skeleton_card(), expand=True)], spacing=6),
            ft.Row([ft.Container(skeleton_card(), expand=True), ft.Container(skeleton_card(), expand=True)], spacing=6),
        ],
        spacing=6,
    )

    def pintar_tarjetas():
        r = resumen()
        tarjetas.controls = [
            ft.Row([ft.Container(tarjeta("💰 Dinero en caja", money(r["caja"]), ft.Colors.TEAL_800, True), expand=True)]),
            ft.Row([
                ft.Container(tarjeta("🕒 Me deben", money(r["por_cobrar"]), ft.Colors.ORANGE_600), expand=True),
                ft.Container(tarjeta("🛒 Vendido", money(r["vendido"]), ft.Colors.LIGHT_BLUE_700), expand=True),
            ], spacing=6),
            ft.Row([
                ft.Container(tarjeta("💸 Gastos", money(r["gastos"]), ft.Colors.RED_600), expand=True),
                ft.Container(tarjeta("📈 Ganancia", money(r["ganancia"]), ft.Colors.GREEN_700), expand=True),
            ], spacing=6),
        ]

    def confirmar_borrado(tabla, id_, texto):
        async def si(e):
            page.close(dlg)
            try:
                await client.table(tabla).delete().eq("id", id_).execute()
                await refrescar()
            except Exception as ex:
                aviso(f"Error: {ex}", True)

        def no(e):
            page.close(dlg)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("¿Eliminar?"),
            content=ft.Text(texto),
            actions=[ft.TextButton("Cancelar", on_click=no), ft.FilledButton("Eliminar", on_click=si)],
        )
        page.open(dlg)

    def campo(label, **kw):
        return ft.TextField(
            label=label,
            border_radius=12,
            filled=True,
            bgcolor=ft.Colors.WHITE,
            border_color=ft.Colors.GREY_300,
            focused_border_color=ft.Colors.TEAL_700,
            text_size=15,
            content_padding=12,
            **kw
        )

    # ==================== GENERADOR DE PDF Y TICKET DIGITAL ====================
    async def generar_pdf_reporte(e=None):
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

            nombre_pdf = f"Reporte_Mi_Negocio_{date.today().strftime('%Y%m%d')}.pdf"
            ruta_pdf = os.path.join(tempfile.gettempdir(), nombre_pdf)

            doc = SimpleDocTemplate(
                ruta_pdf,
                pagesize=A4,
                rightMargin=30,
                leftMargin=30,
                topMargin=30,
                bottomMargin=30,
            )
            elementos = []
            styles = getSampleStyleSheet()

            # Estilos personalizados
            titulo_style = ParagraphStyle("Titulo", parent=styles["Heading1"], fontSize=20, textColor=colors.HexColor("#004D40"), spaceAfter=10)
            sub_style = ParagraphStyle("Subtitulo", parent=styles["Normal"], fontSize=10, textColor=colors.gray, spaceAfter=20)
            h2_style = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=14, textColor=colors.HexColor("#004D40"), spaceBefore=15, spaceAfter=10)

            elementos.append(Paragraph("<b>🏪 Reporte General - Mi Negocio</b>", titulo_style))
            elementos.append(Paragraph(f"Fecha de emisión: {date.today().strftime('%d/%m/%Y')}", sub_style))

            # Tabla Resumen
            r = resumen()
            data_resumen = [
                ["Indicador Financiero", "Monto"],
                ["Capital Inicial", money(r["capital"])],
                ["Total Vendido", money(r["vendido"])],
                ["Total Cobrado", money(r["cobrado"])],
                ["Por Cobrar (Fiados)", money(r["por_cobrar"])],
                ["Gastos Totales", money(r["gastos"])],
                ["Ganancia Neta", money(r["ganancia"])],
                ["Dinero en Caja Actual", money(r["caja"])],
            ]

            t_resumen = Table(data_resumen, colWidths=[280, 200])
            t_resumen.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#004D40")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
                    ]
                )
            )
            elementos.append(t_resumen)

            # Tabla de Ventas Recientes
            elementos.append(Paragraph("<b>Últimas Ventas</b>", h2_style))
            data_ventas = [["Fecha", "Cliente", "Total", "Estado"]]
            for v in estado["ventas"][:15]:
                data_ventas.append([v["fecha"], v["cliente"], money(v["total"]), v["estado"]])

            if len(data_ventas) > 1:
                t_ventas = Table(data_ventas, colWidths=[100, 200, 90, 90])
                t_ventas.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0288D1")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                            ("ALIGN", (3, 0), (3, -1), "CENTER"),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
                        ]
                    )
                )
                elementos.append(t_ventas)
            else:
                elementos.append(Paragraph("No hay ventas registradas aún.", styles["Normal"]))

            doc.build(elementos)

            # Intentar abrir con el visor de PDF nativo del teléfono
            page.launch_url(f"file://{ruta_pdf}")
            aviso("PDF generado correctamente 📄")

        except Exception as ex:
            aviso(f"Error al generar PDF: {ex}", True)

    def mostrar_ticket_modal(e=None):
        r = resumen()
        contenido_ticket = ft.Column(
            [
                ft.Text("🏪 TICKET RESUMEN", size=18, weight=ft.FontWeight.BOLD, color=VERDE),
                ft.Text(f"Fecha: {date.today().strftime('%d/%m/%Y')}", size=12, color=ft.Colors.GREY_700),
                ft.Divider(),
                ft.Row([ft.Text("Dinero en Caja:"), ft.Text(money(r['caja']), weight=ft.FontWeight.BOLD)]),
                ft.Row([ft.Text("Vendido Total:"), ft.Text(money(r['vendido']))]),
                ft.Row([ft.Text("Cobrado:"), ft.Text(money(r['cobrado']))]),
                ft.Row([ft.Text("Por Cobrar (Fiados):"), ft.Text(money(r['por_cobrar']), color=ft.Colors.RED_700)]),
                ft.Row([ft.Text("Gastos Totales:"), ft.Text(money(r['gastos']))]),
                ft.Row([ft.Text("Ganancia Neta:"), ft.Text(money(r['ganancia']), color=ft.Colors.GREEN_700, weight=ft.FontWeight.BOLD)]),
            ],
            tight=True,
            spacing=6,
        )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Resumen Digital"),
            content=contenido_ticket,
            actions=[
                ft.TextButton("Cerrar", on_click=lambda e: page.close(dlg)),
                ft.FilledButton("Descargar PDF", icon=ft.Icons.PICTURE_AS_PDF, on_click=generar_pdf_reporte, bgcolor=ft.Colors.TEAL_800),
            ],
        )
        page.open(dlg)

    # ======================================================================
    #                               VENTAS CON CARRITO
    # ======================================================================
    def al_cambiar_producto(e=None):
        if v_producto.value:
            p = next((x for x in estado["productos"] if x["nombre"] == v_producto.value), None)
            if p and p["precio"] is not None:
                v_precio.value = f"{p['precio']:g}"
            else:
                v_precio.value = ""
        else:
            v_precio.value = ""
        page.update()

    v_fecha = campo("Fecha (AAAA-MM-DD)", value=str(date.today()), keyboard_type=ft.KeyboardType.DATETIME, expand=True)
    btn_cal_ventas = ft.IconButton(
        icon=ft.Icons.CALENDAR_MONTH,
        icon_color=ft.Colors.TEAL_800,
        tooltip="Elegir fecha",
        on_click=lambda _: abrir_calendario(v_fecha),
    )

    v_cliente = campo("Nombre del cliente", capitalization=ft.TextCapitalization.WORDS)
    v_producto = ft.Dropdown(
        label="Producto",
        hint_text="Seleccionar...",
        border_radius=12,
        filled=True,
        bgcolor=ft.Colors.WHITE,
        border_color=ft.Colors.GREY_300,
        focused_border_color=ft.Colors.TEAL_700,
        text_size=15,
        content_padding=12,
        options=[],
        on_change=al_cambiar_producto,
        expand=True,
    )
    v_cantidad = campo("Cant.", value="1", keyboard_type=ft.KeyboardType.NUMBER, width=90)
    v_precio = campo("Precio U.", keyboard_type=ft.KeyboardType.NUMBER, expand=True)
    v_monto_pago = campo("¿Cuánto paga hoy? (S/)", keyboard_type=ft.KeyboardType.NUMBER)

    lista_items_carrito = ft.Column(spacing=2)
    txt_subtotal_carrito = ft.Text("Total Venta: S/ 0.00", size=16, weight=ft.FontWeight.BOLD, color=VERDE)

    def actualizar_ui_carrito():
        lista_items_carrito.controls.clear()
        tot = round(sum(i["subtotal"] for i in carrito_actual), 2)
        for idx, item in enumerate(carrito_actual):
            lista_items_carrito.controls.append(
                ft.Row([
                    ft.Text(f"• {item['cant']}x {item['prod']}", size=14, expand=True),
                    ft.Text(money(item['subtotal']), size=14, weight=ft.FontWeight.BOLD),
                    ft.IconButton(ft.Icons.CLOSE, icon_size=18, icon_color=ft.Colors.RED_400, on_click=lambda e, i=idx: quitar_item(i))
                ])
            )
        txt_subtotal_carrito.value = f"Total Venta: {money(tot)}"
        page.update()

    def quitar_item(idx):
        carrito_actual.pop(idx)
        actualizar_ui_carrito()

    def agregar_al_carrito_click(e):
        cant = num(v_cantidad.value)
        prec = num(v_precio.value)
        if not v_producto.value or not cant or cant <= 0 or prec is None or prec < 0:
            aviso("Selecciona producto, cantidad y precio válido", True)
            return
        
        carrito_actual.append({
            "prod": v_producto.value,
            "cant": cant,
            "precio": prec,
            "subtotal": round(cant * prec, 2)
        })
        v_producto.value = None
        v_cantidad.value = "1"
        v_precio.value = ""
        actualizar_ui_carrito()

    lista_ventas = ft.Column(spacing=0)
    lista_ventas.controls = skeleton_list()

    btn_guardar_venta = ft.FilledButton(
        "Guardar venta completa",
        icon=ft.Icons.CHECK,
        height=48,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12), bgcolor=ft.Colors.TEAL_800),
        expand=True,
    )

    async def guardar_venta(e):
        if not carrito_actual:
            aviso("Agrega al menos un producto al ticket", True)
            return

        total_venta = round(sum(i["subtotal"] for i in carrito_actual), 2)
        monto_pagado = round(num(v_monto_pago.value, 0.0), 2)

        if monto_pagado < 0 or monto_pagado > total_venta:
            aviso("El monto pagado no es válido", True)
            return

        estado_pago = "PAGADO" if abs(monto_pagado - total_venta) < 0.01 else ("PARCIAL" if monto_pagado > 0 else "PENDIENTE")

        btn_guardar_venta.disabled = True
        btn_guardar_venta.content = ft.ProgressRing(width=20, height=20, stroke_width=2, color=ft.Colors.WHITE)
        page.update()

        try:
            res = await client.table("ventas_v2").insert({
                "fecha": v_fecha.value or str(date.today()),
                "cliente": (v_cliente.value or "").strip() or "Cliente General",
                "total": total_venta,
                "estado": estado_pago
            }).execute()
            venta_id = res.data[0]["id"]

            items_db = [{
                "venta_id": venta_id,
                "producto": item["prod"],
                "cantidad": item["cant"],
                "precio_unitario": item["precio"],
                "subtotal": item["subtotal"]
            } for item in carrito_actual]
            await client.table("venta_items").insert(items_db).execute()

            if monto_pagado > 0:
                await client.table("pagos").insert({
                    "venta_id": venta_id,
                    "fecha": v_fecha.value or str(date.today()),
                    "monto": monto_pagado
                }).execute()

            carrito_actual.clear()
            v_cliente.value = ""
            v_monto_pago.value = ""
            actualizar_ui_carrito()
            aviso("¡Venta guardada exitosamente! ✅")
            await refrescar()

        except Exception as ex:
            aviso(f"Error: {ex}", True)
        finally:
            btn_guardar_venta.disabled = False
            btn_guardar_venta.content = None
            page.update()

    btn_guardar_venta.on_click = guardar_venta

    def abrir_dialogo_abono(venta, saldo_pendiente):
        input_monto = campo("Monto que te paga hoy (S/)", value=f"{saldo_pendiente:g}", keyboard_type=ft.KeyboardType.NUMBER)
        
        async def confirmar_pago(e):
            monto_abono = round(num(input_monto.value, 0.0), 2)
            if monto_abono <= 0 or monto_abono > saldo_pendiente + 0.01:
                aviso("Ingresa un monto válido que no exceda la deuda", True)
                return
            
            page.close(dlg)
            try:
                await client.table("pagos").insert({
                    "venta_id": venta["id"],
                    "fecha": str(date.today()),
                    "monto": monto_abono
                }).execute()

                pagos_previos = round(sum(p["monto"] for p in estado["pagos"] if p["venta_id"] == venta["id"]), 2)
                nuevo_total_pagado = round(pagos_previos + monto_abono, 2)
                nuevo_estado = "PAGADO" if nuevo_total_pagado >= round(venta["total"] - 0.01, 2) else "PARCIAL"

                await client.table("ventas_v2").update({"estado": nuevo_estado}).eq("id", venta["id"]).execute()
                aviso("¡Pago/Abono registrado correctamente! 💸")
                await refrescar()
            except Exception as ex:
                aviso(f"Error al registrar pago: {ex}", True)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Abono de {venta['cliente']}"),
            content=ft.Column([
                ft.Text(f"Total venta: {money(venta['total'])}"),
                ft.Text(f"Saldo pendiente: {money(saldo_pendiente)}", color=ft.Colors.RED_700, weight=ft.FontWeight.BOLD),
                input_monto
            ], tight=True, spacing=10),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: page.close(dlg)),
                ft.FilledButton("Guardar Pago", on_click=confirmar_pago, bgcolor=ft.Colors.GREEN_800)
            ]
        )
        page.open(dlg)

    def pintar_ventas():
        if not estado["ventas"]:
            lista_ventas.controls = [ft.Text("Aún no hay ventas. Registra la primera arriba 👆", color=ft.Colors.GREY)]
            return
        items = []
        for v in estado["ventas"][:LIMITE_LISTA]:
            pagos_hechos = round(sum(p["monto"] for p in estado["pagos"] if p["venta_id"] == v["id"]), 2)
            falta = round(v["total"] - pagos_hechos, 2)
            pagado_completo = v["estado"] == "PAGADO" or falta <= 0.01

            acciones_row = [
                ft.IconButton(
                    ft.Icons.DELETE_OUTLINE,
                    icon_size=24,
                    on_click=lambda e, i=v["id"], t=f"{v['cliente']} · {money(v['total'])}":
                        confirmar_borrado("ventas_v2", i, t),
                )
            ]

            if not pagado_completo:
                acciones_row.insert(0, ft.TextButton(
                    "💸 Registrar Pago",
                    icon=ft.Icons.ATTACH_MONEY,
                    icon_color=ft.Colors.GREEN_700,
                    on_click=lambda e, venta=v, f=falta: abrir_dialogo_abono(venta, f)
                ))

            items.append(
                ft.Card(
                    content=ft.Container(
                        border=ft.border.only(left=ft.BorderSide(6, ft.Colors.GREEN if pagado_completo else ft.Colors.ORANGE)),
                        border_radius=12,
                        padding=ft.padding.only(left=8, right=8, top=4, bottom=4),
                        content=ft.Column(
                            [
                                ft.ListTile(
                                    content_padding=0,
                                    leading=ft.Icon(
                                        ft.Icons.CHECK_CIRCLE if pagado_completo else ft.Icons.SCHEDULE,
                                        color=ft.Colors.GREEN if pagado_completo else ft.Colors.ORANGE,
                                        size=28,
                                    ),
                                    title=ft.Text(f"{v['cliente']}", weight=ft.FontWeight.W_500, size=15),
                                    subtitle=ft.Text(f"{v['fecha']} · Estado: {v['estado']}" + (f" (Falta {money(falta)})" if falta > 0.01 else "")),
                                    trailing=ft.Text(money(v["total"]), size=16, weight=ft.FontWeight.BOLD),
                                ),
                                ft.Row(acciones_row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN if len(acciones_row) > 1 else ft.MainAxisAlignment.END),
                            ],
                            spacing=0,
                        ),
                    )
                )
            )
        lista_ventas.controls = items

    tab_ventas = ft.Column(
        [
            ft.Card(
                content=ft.Container(
                    padding=14,
                    content=ft.Column(
                        [
                            ft.Text("Nueva venta (Multiproducto)", size=18, weight=ft.FontWeight.BOLD),
                            ft.Row([v_fecha, btn_cal_ventas], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            v_cliente,
                            ft.Row([v_producto]),
                            ft.Row([v_cantidad, v_precio], spacing=8),
                            ft.OutlinedButton("＋ Agregar al ticket", on_click=agregar_al_carrito_click),
                            ft.Divider(),
                            lista_items_carrito,
                            txt_subtotal_carrito,
                            v_monto_pago,
                            ft.Row([btn_guardar_venta]),
                        ],
                        spacing=10,
                    ),
                )
            ),
            lista_ventas,
        ],
        scroll=ft.ScrollMode.AUTO, expand=True, spacing=8,
    )

    # ======================================================================
    #                               GASTOS
    # ======================================================================
    g_fecha = campo("Fecha (AAAA-MM-DD)", value=str(date.today()), keyboard_type=ft.KeyboardType.DATETIME, expand=True)
    btn_cal_gastos = ft.IconButton(
        icon=ft.Icons.CALENDAR_MONTH,
        icon_color=ft.Colors.TEAL_800,
        tooltip="Elegir fecha",
        on_click=lambda _: abrir_calendario(g_fecha),
    )
    g_concepto = campo("¿En qué gastaste?", capitalization=ft.TextCapitalization.SENTENCES)
    g_monto = campo("Monto", keyboard_type=ft.KeyboardType.NUMBER)
    lista_gastos = ft.Column(spacing=0)
    lista_gastos.controls = skeleton_list()

    btn_guardar_gasto = ft.FilledButton("Guardar gasto", icon=ft.Icons.ADD, height=48, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12), bgcolor=ft.Colors.TEAL_800), expand=True)

    async def guardar_gasto(e):
        monto = round(num(g_monto.value, 0.0), 2)
        if not g_concepto.value or monto <= 0:
            aviso("Escribe el concepto y un monto mayor a cero", True)
            return

        btn_guardar_gasto.disabled = True
        btn_guardar_gasto.content = ft.ProgressRing(width=20, height=20, stroke_width=2, color=ft.Colors.WHITE)
        page.update()

        try:
            await client.table("gastos").insert({"fecha": g_fecha.value or str(date.today()), "concepto": g_concepto.value.strip(), "monto": monto}).execute()
            g_concepto.value, g_monto.value = "", ""
            aviso("Gasto guardado ✅")
            await refrescar()
        except Exception as ex:
            aviso(f"Error: {ex}", True)
        finally:
            btn_guardar_gasto.disabled = False
            btn_guardar_gasto.content = None
            page.update()

    btn_guardar_gasto.on_click = guardar_gasto

    def pintar_gastos():
        if not estado["gastos"]:
            lista_gastos.controls = [ft.Text("Aún no hay gastos.", color=ft.Colors.GREY)]
            return
        lista_gastos.controls = [
            ft.Card(
                content=ft.ListTile(
                    leading=ft.Icon(ft.Icons.PAYMENTS_OUTLINED, color=ft.Colors.RED_400, size=28),
                    title=ft.Text(g["concepto"], weight=ft.FontWeight.W_500, size=15, overflow=ft.TextOverflow.ELLIPSIS),
                    subtitle=ft.Text(g["fecha"]),
                    trailing=ft.Row([
                        ft.Text(money(g["monto"] or 0), size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_600),
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=24, on_click=lambda e, i=g["id"], t=f"{g['concepto']} · {money(g['monto'] or 0)}": confirmar_borrado("gastos", i, t)),
                    ], tight=True),
                )
            )
            for g in estado["gastos"][:LIMITE_LISTA]
        ]

    tab_gastos = ft.Column([
        ft.Card(content=ft.Container(padding=14, content=ft.Column([
            ft.Text("Nuevo gasto", size=18, weight=ft.FontWeight.BOLD),
            ft.Row([g_fecha, btn_cal_gastos], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            g_concepto, g_monto,
            ft.Row([btn_guardar_gasto]),
        ], spacing=10))),
        lista_gastos,
    ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=8)

    # ======================================================================
    #                             PRODUCTOS
    # ======================================================================
    p_nombre = campo("Nombre", capitalization=ft.TextCapitalization.WORDS)
    p_precio = campo("Precio de venta", keyboard_type=ft.KeyboardType.NUMBER, expand=True)
    p_costo = campo("Lo que me cuesta", keyboard_type=ft.KeyboardType.NUMBER, expand=True)
    lista_productos = ft.Column(spacing=0)
    lista_productos.controls = skeleton_list()

    btn_guardar_producto = ft.FilledButton("Guardar producto", icon=ft.Icons.ADD, height=48, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12), bgcolor=ft.Colors.TEAL_800), expand=True)

    async def guardar_producto(e):
        nombre, precio = (p_nombre.value or "").strip(), num(p_precio.value)
        if not nombre or precio is None or precio < 0:
            aviso("Escribe un nombre y un precio válido", True)
            return

        btn_guardar_producto.disabled = True
        btn_guardar_producto.content = ft.ProgressRing(width=20, height=20, stroke_width=2, color=ft.Colors.WHITE)
        page.update()

        try:
            await client.table("productos").upsert({"nombre": nombre, "precio": precio, "costo": num(p_costo.value, 0)}, on_conflict="nombre").execute()
            p_nombre.value, p_precio.value, p_costo.value = "", "", ""
            aviso("Producto guardado ✅")
            await refrescar()
        except Exception as ex:
            aviso(f"Error: {ex}", True)
        finally:
            btn_guardar_producto.disabled = False
            btn_guardar_producto.content = None
            page.update()

    btn_guardar_producto.on_click = guardar_producto

    def pintar_productos():
        if not estado["productos"]:
            lista_productos.controls = [ft.Text("Agrega tus productos arriba para empezar 👆", color=ft.Colors.GREY)]
            return

        def editar(p):
            p_nombre.value, p_precio.value, p_costo.value = p["nombre"], f"{p['precio']:g}", f"{(p['costo'] or 0):g}"
            page.update()

        lista_productos.controls = [
            ft.Card(
                content=ft.ListTile(
                    leading=ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, color=VERDE, size=28),
                    title=ft.Text(p["nombre"], weight=ft.FontWeight.W_500, size=15, overflow=ft.TextOverflow.ELLIPSIS),
                    subtitle=ft.Text(f"Precio {money(p['precio'] or 0)} · Me cuesta {money(p['costo'] or 0)}\nGano {money((p['precio'] or 0) - (p['costo'] or 0))}", overflow=ft.TextOverflow.ELLIPSIS),
                    is_three_line=True,
                    on_click=lambda e, p=p: editar(p),
                    trailing=ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=24, on_click=lambda e, i=p["id"], t=p["nombre"]: confirmar_borrado("productos", i, t)),
                )
            )
            for p in sorted(estado["productos"], key=lambda x: x["nombre"].lower())
        ]

    tab_productos = ft.Column([
        ft.Card(content=ft.Container(padding=14, content=ft.Column([
            ft.Text("Producto (si ya existe, se actualiza)", size=18, weight=ft.FontWeight.BOLD),
            p_nombre,
            ft.Row([p_precio, p_costo], spacing=8),
            ft.Row([btn_guardar_producto]),
        ], spacing=10))),
        ft.Text("Toca un producto para editarlo", size=12, color=ft.Colors.GREY),
        lista_productos,
    ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=8)

    # ======================================================================
    #                               CAPITAL
    # ======================================================================
    c_capital = campo("Capital inicial", keyboard_type=ft.KeyboardType.NUMBER)
    btn_guardar_capital = ft.FilledButton("Guardar capital", icon=ft.Icons.SAVE, height=48, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12), bgcolor=ft.Colors.TEAL_800), expand=True)

    async def guardar_capital(e):
        valor = num(c_capital.value)
        if valor is None:
            aviso("Escribe un número válido", True)
            return

        btn_guardar_capital.disabled = True
        btn_guardar_capital.content = ft.ProgressRing(width=20, height=20, stroke_width=2, color=ft.Colors.WHITE)
        page.update()

        try:
            await client.table("config").upsert({"clave": "capital", "valor": valor}, on_conflict="clave").execute()
            aviso("Capital actualizado ✅")
            await refrescar()
        except Exception as ex:
            aviso(f"Error: {ex}", True)
        finally:
            btn_guardar_capital.disabled = False
            btn_guardar_capital.content = None
            page.update()

    btn_guardar_capital.on_click = guardar_capital

    tab_capital = ft.Column([
        ft.Card(content=ft.Container(padding=14, content=ft.Column([
            ft.Text("Configuración", size=18, weight=ft.FontWeight.BOLD),
            c_capital,
            ft.Row([btn_guardar_capital]),
        ], spacing=10))),
        ft.Card(content=ft.Container(padding=14, content=ft.Column([
            ft.Text("Reportes y Comprobantes", size=18, weight=ft.FontWeight.BOLD),
            ft.Text("Genera un resumen digital rápido en pantalla o descarga un documento PDF.", size=13, color=ft.Colors.GREY_700),
            ft.Row([
                ft.FilledButton("Ver Ticket Digital", icon=ft.Icons.RECEIPT_LONG, on_click=mostrar_ticket_modal, bgcolor=ft.Colors.TEAL_800, expand=True),
            ]),
        ], spacing=10))),
    ], scroll=ft.ScrollMode.AUTO, expand=True, spacing=8)

    # ======================================================================
    #                      REFRESCO Y CONTROL DE CONEXIÓN
    # ======================================================================
    async def refrescar():
        nonlocal carga_inicial
        async with lock:
            try:
                cfg = await client.table("config").select("valor").eq("clave", "capital").execute()
                estado["capital"] = float(cfg.data[0]["valor"]) if cfg.data else 0.0
                estado["productos"] = await traer_todo(client, "productos")
                estado["ventas"] = await traer_todo(client, "ventas_v2")
                estado["pagos"] = await traer_todo(client, "pagos")
                estado["gastos"] = await traer_todo(client, "gastos")
                set_conexion(True)
            except Exception:
                set_conexion(False)
                if carga_inicial:
                    mensaje = ft.Text("No se pudieron cargar los datos. Toca actualizar para reintentar.", color=ft.Colors.GREY_700)
                    tarjetas.controls = [mensaje]
                    lista_ventas.controls = [ft.Text(mensaje.value, color=ft.Colors.GREY_700)]
                    lista_gastos.controls = [ft.Text(mensaje.value, color=ft.Colors.GREY_700)]
                    lista_productos.controls = [ft.Text(mensaje.value, color=ft.Colors.GREY_700)]
                    carga_inicial = False
                    page.update()
                return

            pintar_tarjetas()
            pintar_ventas()
            pintar_gastos()
            pintar_productos()

            nombres = [p["nombre"] for p in sorted(estado["productos"], key=lambda x: x["nombre"].lower())]
            v_producto.options = [ft.dropdown.Option(n) for n in nombres]

            if v_producto.value not in nombres:
                v_producto.value = None
                v_precio.value = ""

            if not c_capital.value:
                c_capital.value = f"{estado['capital']:g}"
            carga_inicial = False
            page.update()

    def hay_cambio(payload):
        page.run_task(refrescar)

    async def suscribir_tiempo_real():
        try:
            canal = client.channel("mi-negocio")
            for t in TABLAS:
                canal.on_postgres_changes("*", callback=hay_cambio, table=t, schema="public")
            await canal.subscribe()
        except Exception:
            set_conexion(False)

    async def sondeo():
        while True:
            await asyncio.sleep(20)
            await refrescar()

    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=250,
        expand=True,
        tabs=[
            ft.Tab(text="Ventas", icon=ft.Icons.SHOPPING_CART, content=ft.Container(tab_ventas, padding=4)),
            ft.Tab(text="Gastos", icon=ft.Icons.PAYMENTS, content=ft.Container(tab_gastos, padding=4)),
            ft.Tab(text="Productos", icon=ft.Icons.INVENTORY_2, content=ft.Container(tab_productos, padding=4)),
            ft.Tab(text="Capital", icon=ft.Icons.SETTINGS, content=ft.Container(tab_capital, padding=4)),
        ],
    )

    page.controls.clear()
    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Container(
                width=480,
                content=ft.Column([
                    ft.Row([
                        ft.Text("🏪 Mi Negocio", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.TEAL_900),
                        ft.Row([
                            ft.IconButton(
                                icon=ft.Icons.REFRESH,
                                tooltip="Recargar datos",
                                icon_color=ft.Colors.TEAL_800,
                                icon_size=22,
                                on_click=lambda _: page.run_task(refrescar)
                            ),
                            badge_conexion,
                        ], spacing=2),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    tarjetas,
                    tabs,
                ], expand=True, spacing=6),
            )
        )
    )

    page.run_task(refrescar)
    await suscribir_tiempo_real()
    page.run_task(sondeo)


ft.app(target=main)
