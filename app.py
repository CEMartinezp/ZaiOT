import os
import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from logic import calculate_ot_premium, apply_phaseout
from fpdf import FPDF
from PyPDF2 import PdfMerger
from io import BytesIO

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
WORKER_BASE   = "https://obbb-tax-calculator.joncamacaro.workers.dev"
VALIDATE_URL  = f"{WORKER_BASE}/validate-token"
CONSUME_URL   = f"{WORKER_BASE}/consume-token"
RESEND_URL    = f"{WORKER_BASE}/resend-token"
STRIPE_SINGLE = "https://buy.stripe.com/test_bJe28qfoQ46d4RreBff7i00"
STRIPE_SUB    = "https://buy.stripe.com/test_7sYcN41y0gSZbfP2Sxf7i02"

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
FONT_REG  = os.path.join(BASE_DIR, "fonts", "DejaVuSans.ttf")
FONT_BOLD = os.path.join(BASE_DIR, "fonts", "DejaVuSans-Bold.ttf")

OT_RATE_TOLERANCE = 0.01  # 1% tolerance for rate mismatch

st.set_page_config(
    page_title="ZaiOT - Overtime Deduction Calculator",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ─────────────────────────────────────────────────────────────
# GLOBAL STYLES  (defined once, applied everywhere)
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
div[data-testid="stButton"] > button {
    background-color:#2ecc71!important;color:white!important;border:none!important;
    border-radius:8px!important;font-weight:600!important;padding:0.5rem 1rem!important;
    transition:all 0.2s ease!important;
}
div[data-testid="stButton"] > button:hover  { background-color:#27ae60!important;transform:translateY(-1px); }
div[data-testid="stButton"] > button:active { background-color:#219150!important; }
div[data-testid="stButton"] > button:disabled { background-color:#2ecc71!important;opacity:0.6!important; }
.plan-card-text        { color:var(--text-color)!important; }
.plan-card-sub         { color:var(--secondary-text-color)!important; }
.plan-card-li          { color:var(--text-color)!important;opacity:0.85; }
.plan-card-name-single { color:#4da6ff!important; }
.plan-card-name-sub    { color:#a78bfa!important; }
.landing-title         { color:var(--text-color)!important; }
.landing-subtitle      { color:var(--secondary-text-color)!important; }
.plan-cards-row        { display:flex;align-items:stretch;gap:24px; }
.plan-card             { flex:1;display:flex;flex-direction:column;justify-content:space-between; }
.banner-green {
    border:1px solid #28a745;border-radius:8px;padding:10px 18px;margin-bottom:16px;
    font-size:14px;font-weight:500;
    background:color-mix(in srgb,#28a745 15%,var(--background-color));color:var(--text-color);
}
.banner-yellow {
    border:1px solid #ffc107;border-radius:8px;padding:10px 18px;margin-bottom:16px;
    font-size:14px;font-weight:500;
    background:color-mix(in srgb,#ffc107 15%,var(--background-color));color:var(--text-color);
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# TEXTS
# ─────────────────────────────────────────────────────────────
texts = {
    "es": {
        # Landing
        "landing_title": "ZaiOT — Calculadora de Deducción por Horas Extras",
        "landing_subtitle": "Calcula tu deducción calificada bajo la Ley OBBB 2025 en minutos.",
        "landing_disclaimer": "Esta herramienta ofrece estimaciones con fines informativos. No constituye asesoría fiscal.",
        "plan_single_name": "Pago por uso",
        "plan_single_price": "$5",
        "plan_single_desc": "Ideal para una sola consulta.",
        "plan_single_features": ["1 cálculo total", "Acceso válido por 6 meses o hasta usar", "Reporte PDF descargable"],
        "plan_sub_name": "100 usos mensuales",
        "plan_sub_price": "$60 / mes",
        "plan_sub_desc": "Para contadores o uso frecuente.",
        "plan_sub_features": ["100 cálculos por mes", "Acceso válido 30 días desde la compra", "Renovación manual volviendo a pagar", "Reporte PDF descargable"],
        "btn_buy_single": "Comprar — $5",
        "btn_buy_sub": "Comprar — $60/mes",
        "resend_title": "¿Ya compraste? Recupera tu acceso",
        "resend_placeholder": "tu@email.com",
        "resend_btn": "Reenviar acceso",
        "resend_sending": "Enviando...",
        "resend_success": "Si este correo tiene una compra registrada, recibirás el enlace en breve.",
        "resend_error": "Por favor ingresa un correo válido.",
        # Toasts / banners
        "toast_welcome": "🎉 ¡Pago exitoso! Ya puedes usar la calculadora.",
        "toast_single_consumed": "🔒 Tu uso ha sido consumido. ¡Gracias por usar ZaiOT!",
        "toast_sub_low_5": "⚠️ Te quedan solo 5 usos este mes.",
        "toast_sub_low_1": "⚠️ Te queda solo 1 uso este mes.",
        "toast_sub_exhausted": "🔒 Has agotado todos tus usos del mes. ¡Gracias por usar ZaiOT!",
        "banner_single_active": "✅ Plan: Pago por uso &nbsp;|&nbsp; 1 uso disponible &nbsp;|&nbsp; Vence: {date}",
        "banner_single_used": "🔒 Plan: Pago por uso &nbsp;|&nbsp; Uso ya consumido",
        "banner_sub_active": "✅ Plan: 100 usos mensuales &nbsp;|&nbsp; {uses} usos restantes &nbsp;|&nbsp; Vence: {date}",
        "banner_sub_low": "⚠️ Plan: 100 usos mensuales &nbsp;|&nbsp; {uses} usos restantes &nbsp;|&nbsp; Vence: {date}",
        # Token status
        "token_expired_single": "Tu acceso de pago por uso ha expirado.",
        "token_expired_sub": "Tu suscripción ha expirado o agotó los 100 usos.",
        "token_consumed_single": "Tu cálculo ya fue realizado. Este token de un solo uso ha sido consumido.",
        "token_consumed_sub": "Has agotado todos tus usos del mes.",
        "token_invalid": "Token no válido o no encontrado.",
        "token_buy_again_single": "Comprar nuevo acceso — $5",
        "token_buy_again_sub": "Renovar suscripción — $60/mes",
        "token_recover": "O recupera tu acceso anterior:",
        # Consume errors
        "consume_error": "Error al procesar tu cálculo. Intenta nuevamente.",
        "consume_expired": "Tu acceso expiró entre la validación y el cálculo. Recarga la página.",
        "calc_btn_single_used": "🔒 Ya realizaste tu cálculo. Este token de un solo uso ha sido consumido.",
        "calc_btn_sub_exhausted": "🔒 Has agotado todos tus usos del mes.",
        "calc_uses_remaining": "🔢 Usos restantes: **{uses}**",
        "calc_confirm_check": "Estoy seguro de los datos proporcionados",
        "calc_btn_buy_more": "¿Necesitas más cálculos? Compra otro plan:",
        "calc_btn_buy_single_lbl": "Pago por uso — $5",
        "calc_btn_buy_sub_lbl": "100 usos mensuales — $60/mes",
        "calc_btn_uses_label_single": "1 uso",
        "calc_btn_uses_label_sub": "{uses} usos restantes",
        # Calculator
        "title": "Calculadora de Deducción por Horas Extras Calificadas (Ley OBBB 2025)",
        "desc": "Estimación de la deducción anual máxima aplicable a las horas extras calificadas (hasta $12,500 para declaración individual o $25,000 para declaración conjunta de casados).",
        "step1_title": "Paso 1: Verificación de requisitos básicos (obligatorio)",
        "step1_info": "Complete las preguntas de este paso para verificar si cumple con los requisitos básicos de elegibilidad.",
        "over_40_label": "¿Se compensan las horas trabajadas por encima de 40 semanales con pago de horas extras?",
        "ss_check_label": "¿El contribuyente posee un Número de Seguro Social (SSN) válido para trabajar?",
        "itin_check_label": "¿El contribuyente posee un Número de Identificación Tributaria Individual (ITIN)?",
        "ot_1_5x_label": "¿La mayoría de las horas extras se remuneran con una tarifa de tiempo y medio (1.5x la tarifa regular)?",
        "unlock_message": "De acuerdo con las respuestas proporcionadas, es posible que no se cumplan los requisitos para aplicar la deducción. Se recomienda consultar con un contador profesional antes de continuar.",
        "eligible_blocked_info": "✅ Sus respuestas cumplen con los requisitos básicos de elegibilidad. Las respuestas han sido bloqueadas.",
        "restart_button": "🔄 Comenzar de nuevo",
        "step2_title": "Paso 2: Ingreso de datos de ingresos y horas extras",
        "step2_info": "Ingrese su ingreso total aproximado del año (incluyendo todos los conceptos gravables).",
        "magi_label": "Ingreso total aproximado del año (incluye salario base, horas extras, bonos, etc) ($)",
        "filing_status_label": "Estado civil para efectos de la declaración de impuestos",
        "filing_status_options": ["Soltero(a)", "Cabeza de familia", "Casado(a) presentando declaración conjunta", "Casado(a) presentando declaración por separado"],
        "calculate_button": "Calcular deducción estimada",
        "results_title": "Resultados estimados",
        "footer": "Información actualizada al {date}\nEsta herramienta ofrece únicamente una estimación. Consulte siempre con un profesional de impuestos.",
        "answer_options": ["Sí", "No", "No estoy seguro(a)"],
        "step2_completed_msg": "✅ Paso 2 completado. Puede continuar con el Paso 3.",
        "step3_title": "Paso 3: Selección del método para ingresar datos de horas extras",
        "step3_info": "Seleccione el método más conveniente y complete los campos correspondientes.",
        "choose_method_label": "Seleccione el método para reportar las horas extras",
        "choose_method_options": ["Dispongo del monto total pagado por horas extras (Opción A)", "Dispongo del detalle de horas trabajadas y tarifa regular (Opción B)"],
        "option_a_title": "**Opción A** — Ingreso por monto total pagado",
        "ot_total_1_5_paid_label": "Monto total recibido por horas extras a tiempo y medio durante el año ($)",
        "ot_total_1_5_paid_help": "Sume todos los importes recibidos por concepto de horas extras remuneradas a tarifa de tiempo y medio.",
        "ot_total_2_0_paid_label": "Monto total recibido por horas extras a doble tarifa durante el año ($)",
        "ot_total_2_0_paid_help": "Sume todos los importes recibidos por concepto de horas extras remuneradas al doble de la tarifa regular.",
        "option_b_title": "**Opción B** — Ingreso por horas trabajadas y tarifa regular",
        "regular_rate_label": "Tarifa horaria regular ($ por hora)",
        "regular_rate_help": "Indique el monto que se paga por hora de trabajo regular.",
        "ot_hours_1_5_label": "Horas totales remuneradas a tiempo y medio durante el año",
        "ot_hours_1_5_help": "Registre la suma total de horas extras remuneradas a tarifa de tiempo y medio (1.5x) durante el año.",
        "dt_hours_2_0_label": "Horas totales remuneradas a doble tarifa durante el año",
        "dt_hours_2_0_help": "Registre las horas remuneradas al doble de la tarifa regular.",
        "over_40_help": "Indique si las horas trabajadas por encima de 40 semanales generan un pago adicional.",
        "ot_1_5x_help": "Confirme si la mayor parte del pago adicional por horas extras corresponde a una tarifa de tiempo y medio.",
        "ss_check_help": "La deducción requiere que el contribuyente posea un Número de Seguro Social válido para empleo.",
        "itin_check_help": "La presencia de un ITIN en lugar de un SSN válido impide aplicar esta deducción.",
        # Errors
        "error_empty_option_a": "⚠️ La Opción A está incompleta. Complete al menos uno de los montos.",
        "error_empty_option_b": "⚠️ La Opción B está incompleta. Ingrese la tarifa regular y al menos una cantidad de horas.",
        "error_missing_total_income": "⚠️ Debe ingresar el ingreso total aproximado del año para continuar.",
        "error_income_less_than_ot": "El ingreso total reportado parece ser inferior al monto total pagado por horas extras. Revise sus respuestas.",
        "warning_no_method_chosen": "Debe seleccionar un método de ingreso de horas extras para continuar.",
        "method_hours": "Por horas trabajadas (Opción B)",
        "method_total": "Por monto total pagado (Opción A)",
        # Rate verification
        "actual_rate_1_5_label": "Tarifa real pagada por horas extras a tiempo y medio ($ por hora)",
        "actual_rate_1_5_help": "Ingrese la tarifa exacta que aparece en su recibo de pago por horas extras a 1.5x. Si no aplica, deje en 0.",
        "actual_rate_2_0_label": "Tarifa real pagada por horas extras a doble tarifa ($ por hora)",
        "actual_rate_2_0_help": "Ingrese la tarifa exacta que aparece en su recibo de pago por horas extras a 2.0x. Si no aplica, deje en 0.",
        "rate_mismatch_warning_1_5": "⚠️ La tarifa real ingresada (\\${actual}) difiere de la tarifa esperada (\\${expected} = tarifa regular × 1.5). Esto puede ocurrir si su empleador usa un método de cálculo diferente.",
        "rate_mismatch_warning_2_0": "⚠️ La tarifa real ingresada (\\${actual}) difiere de la tarifa esperada (\\${expected} = tarifa regular × 2.0). Esto puede ocurrir si su empleador usa un método de cálculo diferente.",
        "rate_match_info": "✅ La tarifa real coincide con la tarifa esperada.",
        "ytd_override_label_1_5": "Total acumulado de horas extras a tiempo y medio según su recibo de pago ($)",
        "ytd_override_label_2_0": "Total acumulado de horas extras a doble tarifa según su recibo de pago ($)",
        "ytd_override_help": "Debido a la diferencia de tarifas, use el monto total acumulado del año directamente de su recibo de pago para mayor precisión.",
        "error_ytd_required_1_5": "⚠️ La tarifa real de tiempo y medio no coincide con la esperada. Debe ingresar el total del recibo de pago para continuar.",
        "error_ytd_required_2_0": "⚠️ La tarifa real de doble tarifa no coincide con la esperada. Debe ingresar el total del recibo de pago para continuar.",
        # Results / table
        "data_tab_title": "Desglose completo",
        "data_subtitle": "Desglose completo del cálculo",
        "data_column_concept": "Concepto",
        "data_column_value": "Valor",
        "results_tab_title": "Resultados y deducción estimada",
        "total_deduction_label": "Deducción aplicable en la línea 14 del Schedule 1 (Formulario 1040)",
        "total_deduction_delta": "Monto final a deducir de la base imponible",
        "total_deduction_success": "Esta es la cantidad que puede utilizar en la línea 14 del Schedule 1. 💰",
        "total_deduction_no_limit": "**Puede deducir {}** correspondiente al pago adicional por horas extras calificadas.",
        "total_deduction_with_limit": "**Puede deducir {}** por concepto de horas extras (limitado por el nivel de ingresos).",
        "limit_info": "El pago adicional por horas extras ascendió a {}, pero de acuerdo con el ingreso total, el monto máximo deducible es {}. Por ello se ajusta a esta cantidad.",
        "breakdown_subtitle": "Desglose detallado",
        "qoc_gross_label": "Monto total correspondiente al pago adicional por horas extras",
        "phaseout_limit_label": "Límite máximo deducible según nivel de ingresos",
        "final_after_limit_label": "**Deducción final tras aplicar límite máximo permitido**",
        # Table section headers
        "section_eligibility": "📋 Elegibilidad",
        "section_income":      "💰 Ingresos",
        "section_ot_inputs":   "⏱ Datos de horas extras",
        "section_rate_check":  "🔍 Verificación de tarifas",
        "section_ot_totals":   "📊 Totales de horas extras",
        "section_deduction":   "✅ Deducción estimada",
        # Table row labels
        "data_base_salary":               "Salario base estimado",
        "data_method_used":               "Método utilizado",
        "data_ot_total_paid":             "Total pagado por horas extras",
        "data_rate_mismatch":              "Diferencia de tarifa detectada",
        "data_mismatch_none":             "Ninguna",
        "data_source_calculated":         "Calculado (horas × tarifa)",
        "data_source_override":           "Total ingresado desde recibo de pago",
        "data_premium_1_5":               "Pago adicional a 1.5× (deducible)",
        "data_premium_2_0":               "Pago adicional a 2.0× (deducible)",
        "data_qoc_gross":                 "Total prima calificada (antes de límite)",
        "data_concept_expected_rate_1_5": "Tarifa esperada a tiempo y medio (regular × 1.5)",
        "data_concept_expected_rate_2_0": "Tarifa esperada a doble tarifa (regular × 2.0)",
        # PDF
        "spinner_generating_pdf": "Generando reporte PDF...",
        "generate_pdf": "Generar reporte PDF",
        "generated_pdf_success": "Reporte generado exitosamente",
        "generated_pdf_success_info": "El documento ya está listo. Puede descargarlo utilizando el botón inferior.",
        "download_button_now": "Descargar Reporte PDF",
        "download_section_title": "Generación y descarga del reporte",
        "download_name_label": "Nombre completo del contribuyente (aparecerá en el reporte)",
        "download_name_placeholder": "Ejemplo: Juan Pérez",
        "download_docs_label": "Adjuntar documentos de respaldo (W-2, recibos de pago, etc.) – opcional",
        "download_docs_help": "Puede cargar uno o varios archivos PDF. Estos se incorporarán al final del reporte.",
        "pdf_title": "Reporte de Deducción por Horas Extras Calificadas – Ley OBBB 2025",
        "pdf_generated_by": "Hecho por ZaiOT",
        "pdf_date": "Fecha: {}",
        "pdf_user_name": "Nombre del contribuyente:",
        "pdf_used_count": "Documentos adjuntos:",
        "pdf_summary_title": "Desglose completo del cálculo",
        "pdf_evidence_title": "Documentos adjuntos como evidencia",
        "pdf_no_docs": "No se adjuntaron documentos de respaldo.",
        "pdf_docs_attached": "Se adjuntan {} documento(s) como evidencia.",
        "pdf_final_deduction": "DEDUCCIÓN FINAL ESTIMADA: {}",
        "disclaimer_label": "AVISO LEGAL Y DESCARGO DE RESPONSABILIDAD",
        "disclaimer": "**Descargo de responsabilidad:** Esta herramienta tiene únicamente fines informativos y de estimación.",
        "disclaimer_msg": "IMPORTANTE: Esta calculadora genera estimaciones aproximadas de la deducción por horas extras calificadas conforme a la Ley OBBB 2025. No representa asesoría fiscal, legal ni contable. Los resultados son orientativos y no garantizan su aceptación por parte del IRS. Se recomienda consultar con un contador público autorizado antes de incluir cualquier deducción en una declaración de impuestos. El uso de esta herramienta es bajo exclusiva responsabilidad del usuario.",
        "language_label": "🌐 Idioma",
        "language_options": ["Español", "English"],
        "button_continue": "Continuar",
        "error_pdf_generation": "❌ Error al generar el PDF: {}",
    },
    "en": {
        # Landing
        "landing_title": "ZaiOT — Overtime Deduction Calculator",
        "landing_subtitle": "Calculate your qualified deduction under the OBBB Act 2025 in minutes.",
        "landing_disclaimer": "This tool provides estimates for informational purposes only. It does not constitute tax advice.",
        "plan_single_name": "Pay per use",
        "plan_single_price": "$5",
        "plan_single_desc": "Ideal for a one-time consultation.",
        "plan_single_features": ["1 calculation total", "Access valid for 6 months or until used", "Downloadable PDF report"],
        "plan_sub_name": "Monthly 100 uses",
        "plan_sub_price": "$60 / month",
        "plan_sub_desc": "For accountants or frequent use.",
        "plan_sub_features": ["100 calculations per month", "Access valid 30 days from purchase", "Manual renewal by purchasing again", "Downloadable PDF report"],
        "btn_buy_single": "Buy — $5",
        "btn_buy_sub": "Buy — $60/mo",
        "resend_title": "Already purchased? Recover your access",
        "resend_placeholder": "your@email.com",
        "resend_btn": "Resend access",
        "resend_sending": "Sending...",
        "resend_success": "If this email has a registered purchase, you will receive the link shortly.",
        "resend_error": "Please enter a valid email address.",
        # Toasts / banners
        "toast_welcome": "🎉 Payment successful! You can now use the calculator.",
        "toast_single_consumed": "🔒 Your use has been consumed. Thank you for using ZaiOT!",
        "toast_sub_low_5": "⚠️ You have only 5 uses left this month.",
        "toast_sub_low_1": "⚠️ You have only 1 use left this month.",
        "toast_sub_exhausted": "🔒 You have used all your monthly uses. Thank you for using ZaiOT!",
        "banner_single_active": "✅ Plan: Pay per use &nbsp;|&nbsp; 1 use available &nbsp;|&nbsp; Expires: {date}",
        "banner_single_used": "🔒 Plan: Pay per use &nbsp;|&nbsp; Use already consumed",
        "banner_sub_active": "✅ Plan: Monthly 100 uses &nbsp;|&nbsp; {uses} uses remaining &nbsp;|&nbsp; Expires: {date}",
        "banner_sub_low": "⚠️ Plan: Monthly 100 uses &nbsp;|&nbsp; {uses} uses remaining &nbsp;|&nbsp; Expires: {date}",
        # Token status
        "token_expired_single": "Your pay-per-use access has expired.",
        "token_expired_sub": "Your subscription has expired or exhausted all 100 uses.",
        "token_consumed_single": "Your calculation has already been completed. This single-use token has been consumed.",
        "token_consumed_sub": "You have used all your monthly uses.",
        "token_invalid": "Token not valid or not found.",
        "token_buy_again_single": "Buy new access — $5",
        "token_buy_again_sub": "Renew subscription — $60/mo",
        "token_recover": "Or recover your previous access:",
        # Consume errors
        "consume_error": "Error processing your calculation. Please try again.",
        "consume_expired": "Your access expired between validation and calculation. Please reload the page.",
        "calc_btn_single_used": "🔒 Your calculation has already been completed. This single-use token has been consumed.",
        "calc_btn_sub_exhausted": "🔒 You have used all your monthly uses.",
        "calc_uses_remaining": "🔢 Uses remaining: **{uses}**",
        "calc_confirm_check": "I confirm the provided data is accurate",
        "calc_btn_buy_more": "Need more calculations? Purchase another plan:",
        "calc_btn_buy_single_lbl": "Pay per use — $5",
        "calc_btn_buy_sub_lbl": "Monthly 100 uses — $60/mo",
        "calc_btn_uses_label_single": "1 use",
        "calc_btn_uses_label_sub": "{uses} uses remaining",
        # Calculator
        "title": "Qualified Overtime Deduction Calculator (OBBB Act 2025)",
        "desc": "Estimate of the maximum annual deduction applicable to qualified overtime pay (up to $12,500 for single filers or $25,000 for married filing jointly).",
        "step1_title": "Step 1: Basic Eligibility Check (required)",
        "step1_info": "Please answer the questions below to verify if you meet the basic eligibility requirements.",
        "over_40_label": "Are hours worked over 40 per week compensated with overtime pay?",
        "ss_check_label": "Does the taxpayer have a valid Social Security Number (SSN) for employment?",
        "itin_check_label": "Does the taxpayer have an Individual Taxpayer Identification Number (ITIN)?",
        "ot_1_5x_label": "Are most overtime hours paid at time-and-a-half rate (1.5x the regular rate)?",
        "unlock_message": "Based on the responses provided, the requirements for this deduction may not be met. It is recommended to consult a tax professional before proceeding.",
        "eligible_blocked_info": "✅ Your answers meet the basic eligibility requirements. Your responses have been locked.",
        "restart_button": "🔄 Start over",
        "step2_title": "Step 2: Enter Income and Overtime Data",
        "step2_info": "Please enter your approximate total income for the year (including all taxable income).",
        "magi_label": "Approximate total annual income (includes base salary, overtime, bonuses, etc.) ($)",
        "filing_status_label": "Filing status for tax purposes",
        "filing_status_options": ["Single", "Head of Household", "Married Filing Jointly", "Married Filing Separately"],
        "calculate_button": "Calculate Estimated Deduction",
        "results_title": "Estimated Results",
        "footer": "Information updated as of {date}\nThis tool provides an estimate only. Always consult a tax professional.",
        "answer_options": ["Yes", "No", "Not sure"],
        "step2_completed_msg": "✅ Step 2 completed. You may proceed to Step 3.",
        "step3_title": "Step 3: Select Method to Enter Overtime Data",
        "step3_info": "Choose the most convenient method and complete the corresponding fields.",
        "choose_method_label": "Select the method for reporting overtime",
        "choose_method_options": ["I have the total amount paid for overtime (Option A)", "I have the breakdown of hours worked and regular rate (Option B)"],
        "option_a_title": "**Option A** — Total amount paid",
        "ot_total_1_5_paid_label": "Total amount received for time-and-a-half overtime during the year ($)",
        "ot_total_1_5_paid_help": "Sum all amounts received for overtime paid at time-and-a-half rate.",
        "ot_total_2_0_paid_label": "Total amount received for double-time overtime during the year ($)",
        "ot_total_2_0_paid_help": "Sum all amounts received for overtime paid at double the regular rate.",
        "option_b_title": "**Option B** — Hours worked and regular rate",
        "regular_rate_label": "Regular hourly rate ($ per hour)",
        "regular_rate_help": "Enter the amount paid per hour for regular work.",
        "ot_hours_1_5_label": "Total hours paid at time-and-a-half during the year",
        "ot_hours_1_5_help": "Enter the total number of overtime hours paid at 1.5x the regular rate.",
        "dt_hours_2_0_label": "Total hours paid at double time during the year",
        "dt_hours_2_0_help": "Enter hours paid at double the regular rate.",
        "over_40_help": "Indicate whether hours worked over 40 per week are compensated with overtime pay.",
        "ot_1_5x_help": "Confirm whether most overtime premium pay is at the time-and-a-half rate.",
        "ss_check_help": "This deduction requires the taxpayer to have a valid Social Security Number for employment.",
        "itin_check_help": "Having an ITIN instead of a valid SSN prevents eligibility for this deduction.",
        # Errors
        "error_empty_option_a": "⚠️ Option A is incomplete. Please enter at least one amount.",
        "error_empty_option_b": "⚠️ Option B is incomplete. Please enter the regular rate and at least one hour amount.",
        "error_missing_total_income": "⚠️ You must enter the approximate total annual income to continue.",
        "error_income_less_than_ot": "The reported total income seems to be less than the total overtime pay. Please check your answers.",
        "warning_no_method_chosen": "You must select a method for entering overtime data to continue.",
        "method_hours": "By hours worked (Option B)",
        "method_total": "By total amount paid (Option A)",
        # Rate verification
        "actual_rate_1_5_label": "Actual overtime rate paid at time-and-a-half ($ per hour)",
        "actual_rate_1_5_help": "Enter the exact rate shown on your pay stub for 1.5x overtime. Leave at 0 if not applicable.",
        "actual_rate_2_0_label": "Actual overtime rate paid at double time ($ per hour)",
        "actual_rate_2_0_help": "Enter the exact rate shown on your pay stub for 2.0x overtime. Leave at 0 if not applicable.",
        "rate_mismatch_warning_1_5": "⚠️ The actual rate entered (${actual}) differs from the expected rate (${expected} = regular rate × 1.5). This may happen if your employer uses a different calculation method.",
        "rate_mismatch_warning_2_0": "⚠️ The actual rate entered (${actual}) differs from the expected rate (${expected} = regular rate × 2.0). This may happen if your employer uses a different calculation method.",
        "rate_match_info": "✅ Actual rate matches the expected rate.",
        "ytd_override_label_1_5": "Total time-and-a-half overtime from your pay stub ($)",
        "ytd_override_label_2_0": "Total double-time overtime from your pay stub ($)",
        "ytd_override_help": "Due to the rate difference, use the year-to-date total directly from your pay stub for greater accuracy.",
        "error_ytd_required_1_5": "⚠️ The actual time-and-a-half rate does not match the expected rate. You must enter the total from your pay stub to continue.",
        "error_ytd_required_2_0": "⚠️ The actual double-time rate does not match the expected rate. You must enter the total from your pay stub to continue.",
        # Results / table
        "data_tab_title": "Full Breakdown",
        "data_subtitle": "Full Calculation Breakdown",
        "data_column_concept": "Concept",
        "data_column_value": "Value",
        "results_tab_title": "Results and Estimated Deduction",
        "total_deduction_label": "Deduction applicable on line 14 of Schedule 1 (Form 1040)",
        "total_deduction_delta": "Final amount to be deducted from taxable income",
        "total_deduction_success": "This is the amount you can use on line 14 of Schedule 1. 💰",
        "total_deduction_no_limit": "**You may deduct {}** corresponding to qualified overtime premium pay.",
        "total_deduction_with_limit": "**You may deduct {}** for overtime (limited by income level).",
        "limit_info": "The overtime premium amounted to {}, but based on total income, the maximum allowable deduction is {}. The amount has been adjusted accordingly.",
        "breakdown_subtitle": "Detailed Breakdown",
        "qoc_gross_label": "Total qualified overtime premium amount",
        "phaseout_limit_label": "Maximum deductible limit based on income level",
        "final_after_limit_label": "**Final deduction after applying maximum limit**",
        # Table section headers
        "section_eligibility": "📋 Eligibility",
        "section_income":      "💰 Income",
        "section_ot_inputs":   "⏱ Overtime Inputs",
        "section_rate_check":  "🔍 Rate Verification",
        "section_ot_totals":   "📊 Overtime Totals",
        "section_deduction":   "✅ Estimated Deduction",
        # Table row labels
        "data_base_salary":               "Estimated base salary",
        "data_method_used":               "Calculation method used",
        "data_ot_total_paid":             "Total overtime paid",
        "data_rate_mismatch":              "Rate mismatch detected",
        "data_mismatch_none":             "None",
        "data_source_calculated":         "Calculated (hours × rate)",
        "data_source_override":           "Total entered from pay stub",
        "data_premium_1_5":               "Overtime premium at 1.5× (deductible)",
        "data_premium_2_0":               "Overtime premium at 2.0× (deductible)",
        "data_qoc_gross":                 "Total qualified premium (before limit)",
        "data_concept_expected_rate_1_5": "Expected time-and-a-half rate (regular × 1.5)",
        "data_concept_expected_rate_2_0": "Expected double-time rate (regular × 2.0)",
        # PDF
        "spinner_generating_pdf": "Generating PDF report...",
        "generate_pdf": "Generate PDF Report",
        "generated_pdf_success": "Report generated successfully",
        "generated_pdf_success_info": "The document is ready. You may now download the report below.",
        "download_button_now": "Download PDF Report",
        "download_section_title": "Report Generation and Download",
        "download_name_label": "Taxpayer's full name (will appear on the report)",
        "download_name_placeholder": "Example: John Smith",
        "download_docs_label": "Attach supporting documents (W-2, pay stubs, etc.) – optional",
        "download_docs_help": "You may upload one or more PDF files. They will be appended to the generated report.",
        "pdf_title": "Qualified Overtime Deduction Report – OBBB Act 2025",
        "pdf_generated_by": "Made by ZaiOT",
        "pdf_date": "Date: {}",
        "pdf_user_name": "Taxpayer name:",
        "pdf_used_count": "Attached documents:",
        "pdf_summary_title": "Full Calculation Breakdown",
        "pdf_evidence_title": "Supporting Documents Attached",
        "pdf_no_docs": "No supporting documents were attached.",
        "pdf_docs_attached": "{} document(s) attached as evidence.",
        "pdf_final_deduction": "FINAL ESTIMATED DEDUCTION: {}",
        "disclaimer_label": "LEGAL NOTICE AND DISCLAIMER",
        "disclaimer": "**Disclaimer:** This tool is provided for informational and estimation purposes only.",
        "disclaimer_msg": "IMPORTANT: This calculator generates approximate estimates of the qualified overtime deduction under the OBBB Act 2025. It is not tax, legal, or accounting advice. Results are for guidance only and do not guarantee acceptance by the IRS. It is strongly recommended to consult a certified public accountant before claiming any deduction. Use of this tool is at the user's sole responsibility.",
        "language_label": "🌐 Language",
        "language_options": ["Spanish", "English"],
        "button_continue": "Continue",
        "error_pdf_generation": "❌ Error generating PDF: {}",
    }
}

# ─────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────
_DEFAULTS = {
    # Eligibility
    "eligible": False,
    "reset_counter": 0,
    "input_filing_val":  None,
    "input_over40_val":  None,
    "input_ot15x_val":   None,
    "input_ss_val":      None,
    "input_itin_val":    None,
    # Step 2
    "results": None,
    "show_results": False,
    "completed_step_2": False,
    "input_total_income": 0.0,
    # Step 3
    "input_method_index": None,   # 0 = Option A, 1 = Option B
    "input_ot_1_5_total": 0.0,
    "input_ot_2_0_total": 0.0,
    "input_regular_rate": 0.0,
    "input_actual_rate_1_5": 0.0,
    "input_actual_rate_2_0": 0.0,
    "input_ot_hours_1_5": 0.0,
    "input_dt_hours_2_0": 0.0,
    "input_ytd_override_1_5": 0.0,
    "input_ytd_override_2_0": 0.0,
    # PDF
    "pdf_bytes": None,
    # Language
    "language": "es",
    # Token
    "token_valid": None,
    "token_data": None,
    "token_consumed": False,
    "token_uses_left": None,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ─────────────────────────────────────────────────────────────
# LANGUAGE
# ─────────────────────────────────────────────────────────────
t    = texts[st.session_state.language]
lang = st.session_state.language

lang_selected = st.selectbox(
    t["language_label"], t["language_options"],
    index=0 if lang == "es" else 1,
    key="global_language_selector",
)
new_lang = "es" if lang_selected in ("Español", "Spanish") else "en"
if new_lang != lang:
    st.session_state.language = new_lang

t    = texts[st.session_state.language]
lang = st.session_state.language

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def fmt_num(value: float, lang: str, currency="$", decimals=2) -> str:
    """Format a number with locale-aware separators."""
    if value is None:
        return f"{currency}0"
    s = f"{value:,.{decimals}f}"
    if lang == "es":
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{currency}{s}"

def fmt_date(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")

def money_input(label, *, value=0.0, step=100.0, decimals=2, key=None, help=None,
                lang="es", currency="$"):
    """Number input + live formatted preview."""
    col_in, col_prev = st.columns([1.5, 3])
    with col_in:
        num = st.number_input(label, min_value=0.0, value=value, step=step,
                              format=f"%.{decimals}f", key=key, help=help)
    with col_prev:
        st.metric(label=" ", value=f"{currency}0" if num == 0
                  else f"{currency}{fmt_num(num, lang, currency='', decimals=decimals)}")
    return num

def show_buy_buttons(t):
    """Stripe purchase links rendered as buttons."""
    st.markdown(
        f"<p style='color:var(--secondary-text-color);font-size:13px;margin-top:12px;'>"
        f"{t['calc_btn_buy_more']}</p>",
        unsafe_allow_html=True,
    )
    col_a, col_b = st.columns(2)
    _btn = (
        '<a href="{url}" target="_blank" style="display:block;text-align:center;'
        'background:{bg};color:#fff;text-decoration:none;padding:10px 16px;'
        'border-radius:8px;font-size:14px;font-weight:600;">{label}</a>'
    )
    with col_a:
        st.markdown(_btn.format(url=STRIPE_SINGLE, bg="#27ae60",
                                label=t["calc_btn_buy_single_lbl"]), unsafe_allow_html=True)
    with col_b:
        st.markdown(_btn.format(url=STRIPE_SUB, bg="#7b61ff",
                                label=t["calc_btn_buy_sub_lbl"]), unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# TOKEN VALIDATION  (once per session)
# ─────────────────────────────────────────────────────────────
token = st.query_params.get("token")

if token and st.session_state.token_valid is None:
    try:
        r    = requests.get(VALIDATE_URL, params={"token": token}, timeout=8)
        data = r.json()
        if data.get("valid"):
            st.session_state.token_valid     = True
            st.session_state.token_data      = data
            st.session_state.token_uses_left = data.get("uses_left")
            if data.get("is_new"):
                st.session_state.show_welcome_toast = True
        else:
            st.session_state.token_valid = False
            st.session_state.token_data  = data
    except Exception:
        st.session_state.token_valid = False
        st.session_state.token_data  = {"reason": "network_error"}

# ─────────────────────────────────────────────────────────────
# LOGO
# ─────────────────────────────────────────────────────────────
st.markdown("""
<div style='text-align:center;margin-bottom:24px;'>
  <h1 style="font-size:52px;font-weight:800;letter-spacing:2px;margin-bottom:5px;">
    <span style="color:#ff4a66;">Zai</span><span style="color:#747375;">O</span><span style="color:#0282fe;">T</span>
  </h1>
  <p style="color:var(--secondary-text-color);font-size:15px;">OVERTIME DEDUCTION CALCULATOR</p>
</div>
""", unsafe_allow_html=True)

# Toasts
if st.session_state.get("show_welcome_toast"):
    st.toast(t["toast_welcome"], icon="🎉")
    st.session_state.show_welcome_toast = False

_TOAST_MAP = {
    "single_consumed": ("toast_single_consumed", "🔒"),
    "sub_exhausted":   ("toast_sub_exhausted",   "🔒"),
    "sub_low_1":       ("toast_sub_low_1",        "⚠️"),
    "sub_low_5":       ("toast_sub_low_5",        "⚠️"),
}
_tk = st.session_state.get("show_toast")
if _tk and _tk in _TOAST_MAP:
    _msg_key, _icon = _TOAST_MAP[_tk]
    st.toast(t[_msg_key], icon=_icon)
    st.session_state.show_toast = None

# ─────────────────────────────────────────────────────────────
# LANDING PAGE
# ─────────────────────────────────────────────────────────────
def show_landing(reason=None):
    tl = texts[st.session_state.language]

    if reason == "expired":
        plan = (st.session_state.token_data or {}).get("type", "single")
        st.error(tl["token_expired_sub"] if plan == "sub" else tl["token_expired_single"])
    elif reason == "consumed":
        plan = (st.session_state.token_data or {}).get("type", "single")
        st.warning(tl["token_consumed_sub"] if plan == "sub" else tl["token_consumed_single"])
    elif reason == "invalid":
        st.error(tl["token_invalid"])

    st.markdown(f"<h2 class='landing-title' style='text-align:center;margin-bottom:4px;'>{tl['landing_title']}</h2>", unsafe_allow_html=True)
    st.markdown(f"<p class='landing-subtitle' style='text-align:center;margin-bottom:32px;'>{tl['landing_subtitle']}</p>", unsafe_allow_html=True)
    st.caption(tl["landing_disclaimer"])
    st.markdown("---")

    feat_s = "".join(f'<li class="plan-card-li">{f}</li>' for f in tl["plan_single_features"])
    feat_b = "".join(f'<li class="plan-card-li">{f}</li>' for f in tl["plan_sub_features"])

    st.markdown(f"""
    <div class="plan-cards-row">
      <div class="plan-card" style="border:2px solid #1f6fd2;border-radius:12px;padding:28px 24px;text-align:center;">
        <div>
          <h3 class="plan-card-name-single" style="margin-bottom:4px;">{tl["plan_single_name"]}</h3>
          <p class="plan-card-text" style="font-size:36px;font-weight:800;margin:8px 0;">{tl["plan_single_price"]}</p>
          <p class="plan-card-sub" style="font-size:14px;margin-bottom:20px;">{tl["plan_single_desc"]}</p>
          <ul style="text-align:left;font-size:14px;line-height:2;padding-left:20px;margin-bottom:24px;">{feat_s}</ul>
        </div>
        <div style="text-align:center;margin-top:8px;">
          <a href="{STRIPE_SINGLE}" target="_blank"
             style="display:inline-block;background:#27ae60;color:#fff;text-decoration:none;
                    padding:14px 36px;border-radius:10px;font-size:16px;font-weight:700;">{tl["btn_buy_single"]}</a>
        </div>
      </div>
      <div class="plan-card" style="border:2px solid #7b61ff;border-radius:12px;padding:28px 24px;text-align:center;position:relative;">
        <div style="position:absolute;top:-12px;left:50%;transform:translateX(-50%);background:#7b61ff;
                    color:#fff;font-size:11px;font-weight:700;padding:4px 14px;border-radius:20px;">POPULAR</div>
        <div>
          <h3 class="plan-card-name-sub" style="margin-bottom:4px;">{tl["plan_sub_name"]}</h3>
          <p class="plan-card-text" style="font-size:36px;font-weight:800;margin:8px 0;">{tl["plan_sub_price"]}</p>
          <p class="plan-card-sub" style="font-size:14px;margin-bottom:20px;">{tl["plan_sub_desc"]}</p>
          <ul style="text-align:left;font-size:14px;line-height:2;padding-left:20px;margin-bottom:24px;">{feat_b}</ul>
        </div>
        <div style="text-align:center;margin-top:8px;">
          <a href="{STRIPE_SUB}" target="_blank"
             style="display:inline-block;background:#7b61ff;color:#fff;text-decoration:none;
                    padding:14px 36px;border-radius:10px;font-size:16px;font-weight:700;">{tl["btn_buy_sub"]}</a>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(f"<h4 style='text-align:center;'>{tl['resend_title']}</h4>", unsafe_allow_html=True)
    col_e, col_b = st.columns([3, 1])
    with col_e:
        email = st.text_input("email_resend", placeholder=tl["resend_placeholder"],
                              label_visibility="collapsed", key="resend_email_input")
    with col_b:
        if st.button(tl["resend_btn"], use_container_width=True):
            if not email or "@" not in email:
                st.error(tl["resend_error"])
            else:
                with st.spinner(tl["resend_sending"]):
                    try:
                        requests.post(RESEND_URL, json={"email": email}, timeout=8)
                    except Exception:
                        pass
                st.success(tl["resend_success"])

# ─────────────────────────────────────────────────────────────
# ROUTING
# ─────────────────────────────────────────────────────────────
if not token:
    show_landing()
    st.stop()

if st.session_state.token_valid is False:
    reason = (st.session_state.token_data or {}).get("reason", "invalid")
    show_landing(reason=reason if reason in ("expired", "consumed") else "invalid")
    st.stop()

# ─────────────────────────────────────────────────────────────
# PLAN BANNER
# ─────────────────────────────────────────────────────────────
def show_plan_banner():
    td = st.session_state.token_data
    if not td:
        return
    plan_type  = td.get("type", "single")
    exp_date   = fmt_date(td["expires_at"]) if td.get("expires_at") else "—"
    uses_left  = st.session_state.token_uses_left

    if plan_type == "single":
        if st.session_state.token_consumed:
            html = f"<div class='banner-yellow'>{t['banner_single_used']}</div>"
        else:
            html = f"<div class='banner-green'>{t['banner_single_active'].format(date=exp_date)}</div>"
    else:
        uses      = uses_left if uses_left is not None else "?"
        is_low    = isinstance(uses, int) and uses <= 10
        css_class = "banner-yellow" if is_low else "banner-green"
        tpl       = t["banner_sub_low"] if is_low else t["banner_sub_active"]
        html      = f"<div class='{css_class}'>{tpl.format(uses=uses, date=exp_date)}</div>"

    st.markdown(html, unsafe_allow_html=True)

show_plan_banner()

# ─────────────────────────────────────────────────────────────
# CALCULATOR HEADER
# ─────────────────────────────────────────────────────────────
st.title(t["title"])
st.markdown(f"""
<div style="font-size:1.3rem;line-height:1.6;padding:16px;
    background-color:var(--secondary-background-color);
    border-left:6px solid #2196F3;border-radius:4px;color:var(--text-color);">
{t["desc"]}
</div>
""", unsafe_allow_html=True)
st.warning(t["disclaimer"])

# ─────────────────────────────────────────────────────────────
# STEP 1 — ELIGIBILITY
# ─────────────────────────────────────────────────────────────
eligible = st.session_state.eligible

with st.expander(f"### {t['step1_title']}", expanded=not eligible):
    st.info(t["step1_info"])

    # Persist answers as string values so they survive language reruns.
    # We look up the integer index from the current language's option list at render time.
    def _radio_index(saved_key, options):
        """Return the integer index of the saved value in options, or None if not saved."""
        saved = st.session_state.get(saved_key)
        if saved is None:
            return None
        # saved may be an index (int) from a previous session or a string value
        if isinstance(saved, int) and 0 <= saved < len(options):
            return saved
        try:
            return options.index(saved)
        except ValueError:
            return None

    _rc = st.session_state.reset_counter  # bump forces widget recreation

    filing_status = st.radio(
        t["filing_status_label"], t["filing_status_options"],
        index=_radio_index("input_filing_val", t["filing_status_options"]),
        horizontal=True, disabled=eligible, key=f"w_filing_{_rc}",
    )
    st.session_state.input_filing_val = (
        t["filing_status_options"].index(filing_status) if filing_status is not None else None
    )

    over_40 = st.radio(
        t["over_40_label"], t["answer_options"],
        index=_radio_index("input_over40_val", t["answer_options"]),
        horizontal=True, disabled=eligible, help=t["over_40_help"], key=f"w_over40_{_rc}",
    )
    st.session_state.input_over40_val = (
        t["answer_options"].index(over_40) if over_40 is not None else None
    )

    ot_1_5x = st.radio(
        t["ot_1_5x_label"], t["answer_options"],
        index=_radio_index("input_ot15x_val", t["answer_options"]),
        horizontal=True, disabled=eligible, help=t["ot_1_5x_help"], key=f"w_ot15x_{_rc}",
    )
    st.session_state.input_ot15x_val = (
        t["answer_options"].index(ot_1_5x) if ot_1_5x is not None else None
    )

    ss_check = st.radio(
        t["ss_check_label"], t["answer_options"],
        index=_radio_index("input_ss_val", t["answer_options"]),
        horizontal=True, disabled=eligible, help=t["ss_check_help"], key=f"w_ss_{_rc}",
    )
    st.session_state.input_ss_val = (
        t["answer_options"].index(ss_check) if ss_check is not None else None
    )

    itin_check = st.radio(
        t["itin_check_label"], t["answer_options"],
        index=_radio_index("input_itin_val", t["answer_options"]),
        horizontal=True, disabled=eligible, help=t["itin_check_help"], key=f"w_itin_{_rc}",
    )
    st.session_state.input_itin_val = (
        t["answer_options"].index(itin_check) if itin_check is not None else None
    )

    all_answered = all(x is not None for x in [filing_status, over_40, ot_1_5x, ss_check, itin_check])
    auto_eligible = (
        all_answered and
        filing_status != t["filing_status_options"][3] and
        over_40    == t["answer_options"][0] and
        ot_1_5x    == t["answer_options"][0] and
        ss_check   == t["answer_options"][0] and
        itin_check == t["answer_options"][1]
    )

    if auto_eligible and not st.session_state.eligible:
        st.session_state.eligible = True
        st.rerun()

    if eligible:
        st.info(t["eligible_blocked_info"])
    elif all_answered:
        st.warning(t["unlock_message"])
        if st.button(t["restart_button"], type="secondary", use_container_width=True):
            for k in ("input_filing_val", "input_over40_val", "input_ot15x_val",
                      "input_ss_val", "input_itin_val"):
                st.session_state.pop(k, None)
            st.session_state.reset_counter += 1
            st.rerun()

# ─────────────────────────────────────────────────────────────
# STEP 2 — INCOME
# ─────────────────────────────────────────────────────────────
if not eligible:
    st.stop()

with st.expander(f"### {t['step2_title']}", expanded=True):
    st.info(t["step2_info"])
    total_income = money_input(
        t["magi_label"],
        value=st.session_state.input_total_income,
        step=1000.0, lang=lang, key="w_total_income",
    )
    st.session_state.input_total_income = total_income

    if not st.session_state.completed_step_2:
        if st.button(t["button_continue"], type="secondary", use_container_width=True):
            if total_income <= 0:
                st.error(t["error_missing_total_income"])
            else:
                st.session_state.completed_step_2 = True
                st.rerun()
    else:
        st.success(t["step2_completed_msg"])

if not st.session_state.completed_step_2:
    st.stop()

# ─────────────────────────────────────────────────────────────
# STEP 3 — METHOD  (variables initialised here so calculate
#                   button always has them in scope)
# ─────────────────────────────────────────────────────────────
ot_1_5_total = ot_2_0_total = 0.0
regular_rate = ot_hours_1_5 = dt_hours_2_0 = 0.0
actual_rate_1_5 = actual_rate_2_0 = 0.0
expected_rate_1_5 = expected_rate_2_0 = 0.0
ytd_override_1_5 = ytd_override_2_0 = 0.0
mismatch_1_5 = mismatch_2_0 = False
rate_1_5 = rate_2_0 = 0.0

with st.expander(f"### {t['step3_title']}", expanded=True):
    st.info(t["step3_info"])
    method_choice = st.radio(
        t["choose_method_label"], t["choose_method_options"],
        index=st.session_state.input_method_index,
        horizontal=True, key="w_method",
    )
    # Persist selected index (0 or 1) so it survives language reruns
    if method_choice is not None:
        st.session_state.input_method_index = (
            0 if method_choice == t["choose_method_options"][0] else 1
        )

    if not method_choice:
        st.warning(t["warning_no_method_chosen"])
        st.stop()

    if method_choice == t["choose_method_options"][0]:
        # ── Option A ────────────────────────────────────────
        with st.expander(t["option_a_title"], expanded=True):
            ot_1_5_total = money_input(
                t["ot_total_1_5_paid_label"], step=100.0,
                value=st.session_state.input_ot_1_5_total,
                help=t["ot_total_1_5_paid_help"], lang=lang, key="w_ot_1_5_total",
            )
            ot_2_0_total = money_input(
                t["ot_total_2_0_paid_label"], step=100.0,
                value=st.session_state.input_ot_2_0_total,
                help=t["ot_total_2_0_paid_help"], lang=lang, key="w_ot_2_0_total",
            )
            st.session_state.input_ot_1_5_total = ot_1_5_total
            st.session_state.input_ot_2_0_total = ot_2_0_total
    else:
        # ── Option B ────────────────────────────────────────
        with st.expander(t["option_b_title"], expanded=True):
            regular_rate = money_input(
                t["regular_rate_label"], step=0.5,
                value=st.session_state.input_regular_rate,
                help=t["regular_rate_help"], lang=lang, key="w_regular_rate",
            )
            actual_rate_1_5 = money_input(
                t["actual_rate_1_5_label"], step=0.5,
                value=st.session_state.input_actual_rate_1_5,
                help=t["actual_rate_1_5_help"], lang=lang, key="w_actual_rate_1_5",
            )
            actual_rate_2_0 = money_input(
                t["actual_rate_2_0_label"], step=0.5,
                value=st.session_state.input_actual_rate_2_0,
                help=t["actual_rate_2_0_help"], lang=lang, key="w_actual_rate_2_0",
            )
            ot_hours_1_5 = money_input(
                t["ot_hours_1_5_label"], step=5.0, decimals=2,
                value=st.session_state.input_ot_hours_1_5,
                help=t["ot_hours_1_5_help"], lang=lang, currency=" ", key="w_ot_hours_1_5",
            )
            dt_hours_2_0 = money_input(
                t["dt_hours_2_0_label"], step=5.0, decimals=2,
                value=st.session_state.input_dt_hours_2_0,
                help=t["dt_hours_2_0_help"], lang=lang, currency=" ", key="w_dt_hours_2_0",
            )
            # Persist
            st.session_state.input_regular_rate     = regular_rate
            st.session_state.input_actual_rate_1_5  = actual_rate_1_5
            st.session_state.input_actual_rate_2_0  = actual_rate_2_0
            st.session_state.input_ot_hours_1_5     = ot_hours_1_5
            st.session_state.input_dt_hours_2_0     = dt_hours_2_0

            expected_rate_1_5 = regular_rate * 1.5 if regular_rate > 0 else 0.0
            expected_rate_2_0 = regular_rate * 2.0 if regular_rate > 0 else 0.0

            def _is_mismatch(actual, expected):
                return (actual > 0 and expected > 0 and
                        abs(actual - expected) / expected > OT_RATE_TOLERANCE)

            mismatch_1_5 = _is_mismatch(actual_rate_1_5, expected_rate_1_5)
            mismatch_2_0 = _is_mismatch(actual_rate_2_0, expected_rate_2_0)

            # Feedback
            for actual, expected, mismatch, warn_key in [
                (actual_rate_1_5, expected_rate_1_5, mismatch_1_5, "rate_mismatch_warning_1_5"),
                (actual_rate_2_0, expected_rate_2_0, mismatch_2_0, "rate_mismatch_warning_2_0"),
            ]:
                if actual > 0 and expected > 0:
                    if mismatch:
                        st.warning(t[warn_key].format(actual=f"{actual:.2f}",
                                                      expected=f"{expected:.2f}"))
                    else:
                        st.info(t["rate_match_info"])

            # Override inputs (only when mismatch)
            if mismatch_1_5:
                st.markdown("---")
                ytd_override_1_5 = money_input(
                    t["ytd_override_label_1_5"], step=100.0,
                    value=st.session_state.input_ytd_override_1_5,
                    help=t["ytd_override_help"], lang=lang, key="w_ytd_override_1_5",
                )
                st.session_state.input_ytd_override_1_5 = ytd_override_1_5
            if mismatch_2_0:
                if not mismatch_1_5:
                    st.markdown("---")
                ytd_override_2_0 = money_input(
                    t["ytd_override_label_2_0"], step=100.0,
                    value=st.session_state.input_ytd_override_2_0,
                    help=t["ytd_override_help"], lang=lang, key="w_ytd_override_2_0",
                )
                st.session_state.input_ytd_override_2_0 = ytd_override_2_0

# ─────────────────────────────────────────────────────────────
# CALCULATE BUTTON
# ─────────────────────────────────────────────────────────────
td        = st.session_state.token_data or {}
plan_type = td.get("type", "single")
uses_left = st.session_state.token_uses_left
is_single = plan_type == "single"

uses_label = (t["calc_btn_uses_label_single"] if is_single
              else t["calc_btn_uses_label_sub"].format(
                  uses=uses_left if isinstance(uses_left, int) else "?"))
btn_label = f"{t['calculate_button']} ({uses_label})"

if is_single and st.session_state.token_consumed:
    st.info(t["calc_btn_single_used"])
    show_buy_buttons(t)
elif not is_single and isinstance(uses_left, int) and uses_left <= 0:
    st.error(t["calc_btn_sub_exhausted"])
    show_buy_buttons(t)
else:
    confirmed = st.checkbox(t["calc_confirm_check"], key="calc_confirm_checkbox")

    if st.button(btn_label, type="secondary", use_container_width=True, disabled=not confirmed):

        # ── Validations ──────────────────────────────────────
        if total_income <= 0:
            st.error(t["error_missing_total_income"]); st.stop()

        if method_choice == t["choose_method_options"][0]:
            if not (ot_1_5_total > 0 or ot_2_0_total > 0):
                st.error(t["error_empty_option_a"]); st.stop()
            method_used = t["method_total"]
            rate_mismatch_label = "--"

        else:  # Option B
            if not (regular_rate > 0 and (ot_hours_1_5 + dt_hours_2_0) > 0):
                st.error(t["error_empty_option_b"]); st.stop()

            if mismatch_1_5 and ytd_override_1_5 <= 0:
                st.error(t["error_ytd_required_1_5"]); st.stop()
            if mismatch_2_0 and ytd_override_2_0 <= 0:
                st.error(t["error_ytd_required_2_0"]); st.stop()

            method_used = t["method_hours"]
            rate_1_5    = actual_rate_1_5 if actual_rate_1_5 > 0 else regular_rate * 1.5
            rate_2_0    = actual_rate_2_0 if actual_rate_2_0 > 0 else regular_rate * 2.0

            if mismatch_1_5 and ytd_override_1_5 > 0:
                ot_1_5_total = ytd_override_1_5
            else:
                ot_1_5_total = ot_hours_1_5 * rate_1_5

            if mismatch_2_0 and ytd_override_2_0 > 0:
                ot_2_0_total = ytd_override_2_0
            else:
                ot_2_0_total = dt_hours_2_0 * rate_2_0

            if mismatch_1_5 and mismatch_2_0:
                rate_mismatch_label = "1.5× and 2.0×" if lang == "en" else "1.5× y 2.0×"
            elif mismatch_1_5:
                rate_mismatch_label = "1.5×"
            elif mismatch_2_0:
                rate_mismatch_label = "2.0×"
            else:
                rate_mismatch_label = t["data_mismatch_none"]

        # ── Core calculation ─────────────────────────────────
        ot_total_paid  = ot_1_5_total + ot_2_0_total
        ot_1_5_premium = calculate_ot_premium(ot_1_5_total, 1.5, "total")
        ot_2_0_premium = calculate_ot_premium(ot_2_0_total, 2.0, "total")
        qoc_gross      = ot_1_5_premium + ot_2_0_premium

        is_mfj = filing_status == t["filing_status_options"][2]
        max_ded, phase_start, phase_range = (
            (25000, 300000, 250000) if is_mfj else (12500, 150000, 125000)
        )
        deduction_limit = apply_phaseout(magi=total_income, max_value=max_ded,
                                         phase_start=phase_start, phase_range=phase_range)
        total_deduction = min(qoc_gross, deduction_limit)
        base_salary     = total_income - ot_total_paid

        if base_salary < 0:
            st.error(t["error_income_less_than_ot"]); st.stop()

        # ── Consume token ────────────────────────────────────
        if is_single and not st.session_state.token_consumed or not is_single:
            try:
                rc      = requests.post(CONSUME_URL, json={"token": token}, timeout=8)
                rc_data = rc.json()
                if not rc_data.get("success"):
                    err = rc_data.get("reason", "error")
                    st.error(t["consume_expired"] if err == "expired" else t["consume_error"])
                    st.stop()
                if is_single:
                    st.session_state.token_consumed  = True
                    st.session_state.token_uses_left = None
                    st.session_state.show_toast      = "single_consumed"
                else:
                    new_uses = rc_data.get("uses_left")
                    st.session_state.token_uses_left = new_uses
                    st.session_state.show_toast = (
                        "sub_exhausted" if new_uses == 0 else
                        "sub_low_1"     if new_uses == 1 else
                        "sub_low_5"     if new_uses == 5 else None
                    )
            except Exception:
                st.error(t["consume_error"]); st.stop()

        # ── Save results ─────────────────────────────────────
        st.session_state.results = {
            "total_income":      total_income,
            "base_salary":       base_salary,
            "ot_total_paid":     ot_total_paid,
            "ot_1_5_total":      ot_1_5_total,
            "ot_2_0_total":      ot_2_0_total,
            "ot_1_5_premium":    ot_1_5_premium,
            "ot_2_0_premium":    ot_2_0_premium,
            "rate_1_5":          rate_1_5,
            "rate_2_0":          rate_2_0,
            "method_used":       method_used,
            "over_40":           over_40    or "--",
            "ot_1_5x":           ot_1_5x    or "--",
            "ss_check":          ss_check   or "--",
            "filing_status":     filing_status or "--",
            "itin_check":        itin_check or "--",
            "qoc_gross":         qoc_gross,
            "deduction_limit":   deduction_limit,
            "total_deduction":   total_deduction,
            # Option B detail
            "regular_rate":      regular_rate,
            "ot_hours_1_5":      ot_hours_1_5,
            "dt_hours_2_0":      dt_hours_2_0,
            "expected_rate_1_5": expected_rate_1_5,
            "expected_rate_2_0": expected_rate_2_0,
            "actual_rate_1_5":   actual_rate_1_5,
            "actual_rate_2_0":   actual_rate_2_0,
            "mismatch_1_5":      mismatch_1_5,
            "mismatch_2_0":      mismatch_2_0,
            "override_total_1_5":ytd_override_1_5,
            "override_total_2_0":ytd_override_2_0,
            "rate_mismatch_label": rate_mismatch_label,
        }
        st.session_state.show_results = True
        st.rerun()

# ─────────────────────────────────────────────────────────────
# RESULTS
# ─────────────────────────────────────────────────────────────
if not st.session_state.show_results:
    st.stop()

d = st.session_state.results
tab_results, tab_data = st.tabs([t["results_tab_title"], t["data_tab_title"]])

with tab_results:
    st.subheader(t["results_title"])
    qoc_gross       = d["qoc_gross"]
    deduction_limit = d["deduction_limit"]
    total_deduction = d["total_deduction"]

    if qoc_gross <= deduction_limit:
        st.success(t["total_deduction_no_limit"].format(fmt_num(total_deduction, lang)))
    else:
        st.warning(t["total_deduction_with_limit"].format(fmt_num(total_deduction, lang)))
        st.info(t["limit_info"].format(fmt_num(qoc_gross, lang), fmt_num(deduction_limit, lang)))

    st.markdown("---")
    col_l, col_r = st.columns([1, 2])
    with col_l:
        st.metric(label=t["total_deduction_label"],
                  value=fmt_num(total_deduction, lang),
                  delta=t["total_deduction_delta"])
        st.success(t["total_deduction_success"])
    with col_r:
        st.subheader(t["breakdown_subtitle"])
        st.metric(t["qoc_gross_label"],         fmt_num(qoc_gross, lang))
        st.metric(t["phaseout_limit_label"],    fmt_num(deduction_limit, lang))
        st.metric(t["final_after_limit_label"], fmt_num(total_deduction, lang))

with tab_data:
    st.subheader(t["data_subtitle"])
    is_b = d["method_used"] == t["method_hours"]

    def _v(val, *, money=True, hours=False):
        """Return formatted value or '--' for zero/None."""
        if not val:
            return "--"
        if hours:
            return f"{float(val):.0f} h"
        return fmt_num(val, lang) if money else str(val)

    SECTION = "__SEC__"
    rows = []

    rows += [(SECTION, t["section_eligibility"]),
             (t["filing_status_label"], d["filing_status"]),
             (t["ss_check_label"],      d["ss_check"]),
             (t["itin_check_label"],    d["itin_check"]),
             (t["over_40_label"],       d["over_40"]),
             (t["ot_1_5x_label"],       d["ot_1_5x"])]

    rows += [(SECTION, t["section_income"]),
             (t["magi_label"],       fmt_num(d["total_income"], lang)),
             (t["data_base_salary"], fmt_num(d["base_salary"],  lang))]

    rows += [(SECTION, t["section_ot_inputs"]),
             (t["data_method_used"], d["method_used"])]
    if is_b:
        rows += [(t["regular_rate_label"],  _v(d["regular_rate"])),
                 (t["ot_hours_1_5_label"],  _v(d["ot_hours_1_5"], hours=True)),
                 (t["dt_hours_2_0_label"],  _v(d["dt_hours_2_0"], hours=True))]
    else:
        rows += [(t["ot_total_1_5_paid_label"], fmt_num(d["ot_1_5_total"], lang)),
                 (t["ot_total_2_0_paid_label"], fmt_num(d["ot_2_0_total"], lang))]

    if is_b:
        rows += [(SECTION, t["section_rate_check"]),
                 (t["data_concept_expected_rate_1_5"], fmt_num(d["expected_rate_1_5"], lang)),
                 (t["data_concept_expected_rate_2_0"], fmt_num(d["expected_rate_2_0"], lang)),
                 (t["actual_rate_1_5_label"],
                  fmt_num(d["actual_rate_1_5"], lang) if d["actual_rate_1_5"] > 0 else "--"),
                 (t["actual_rate_2_0_label"],
                  fmt_num(d["actual_rate_2_0"], lang) if d["actual_rate_2_0"] > 0 else "--"),
                 (t["data_rate_mismatch"], d["rate_mismatch_label"])]

    rows += [(SECTION, t["section_ot_totals"]),
             (t["ot_total_1_5_paid_label"], fmt_num(d["ot_1_5_total"],  lang)),
             (t["ot_total_2_0_paid_label"], fmt_num(d["ot_2_0_total"],  lang)),
             (t["data_ot_total_paid"],       fmt_num(d["ot_total_paid"], lang)),
             (t["data_premium_1_5"],         fmt_num(d["ot_1_5_premium"], lang)),
             (t["data_premium_2_0"],
              fmt_num(d["ot_2_0_premium"], lang) if d["ot_2_0_premium"] > 0 else "--")]

    rows += [(SECTION, t["section_deduction"]),
             (t["data_qoc_gross"],        fmt_num(d["qoc_gross"],       lang)),
             (t["phaseout_limit_label"],  fmt_num(d["deduction_limit"], lang)),
             (t["total_deduction_label"], fmt_num(d["total_deduction"], lang))]

    # Render
    FINAL_KEY  = t["total_deduction_label"]
    SEC_STYLE  = "background-color:#1e3a5f;color:white;font-weight:700"
    FINAL_STYLE= "background-color:#1a6b3a;color:white;font-weight:700"
    CON, VAL   = t["data_column_concept"], t["data_column_value"]

    styled = []
    for label, value in rows:
        if label == SECTION:
            styled.append({CON: value, VAL: "", "_s": SEC_STYLE})
        elif label == FINAL_KEY:
            styled.append({CON: label,  VAL: value, "_s": FINAL_STYLE})
        else:
            styled.append({CON: label,  VAL: value, "_s": ""})

    df     = pd.DataFrame(styled)
    styles = df.pop("_s").tolist()

    st.dataframe(
        df.style.apply(lambda row: [styles[row.name]] * 2, axis=1),
        use_container_width=True,
        hide_index=True,
        column_config={
            CON: st.column_config.TextColumn(CON, width="large"),
            VAL: st.column_config.TextColumn(VAL, width="medium"),
        }
    )

# ─────────────────────────────────────────────────────────────
# PDF BUILDER
# ─────────────────────────────────────────────────────────────
def build_pdf(user_name, uploaded_files, num_docs, results, lang):
    tl = texts[lang]

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 20, 20)
    pdf.add_font("DejaVu", "",  FONT_REG)
    pdf.add_font("DejaVu", "B", FONT_BOLD)

    UW, LW, VW, RH = 170, 120, 50, 8
    ALT = (245, 245, 245)

    def _sec(text):
        pdf.ln(6)
        pdf.set_fill_color(30, 100, 200); pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 11)
        pdf.cell(UW, 9, text, new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.set_text_color(0, 0, 0); pdf.set_font("DejaVu", "", 10); pdf.ln(1)

    def _hdr(c1, c2):
        x, y = pdf.l_margin, pdf.get_y()
        pdf.set_fill_color(50, 50, 50); pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 10); pdf.set_xy(x, y)
        pdf.cell(LW, RH, c1, fill=True, border=0)
        pdf.cell(VW, RH, c2, fill=True, border=0, align="R",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0); pdf.set_font("DejaVu", "", 10)

    def _row(label, value, idx=0):
        if pdf.get_y() + RH > pdf.h - pdf.b_margin:
            pdf.add_page()
        x, y = pdf.l_margin, pdf.get_y()
        pdf.set_fill_color(*(ALT if idx % 2 == 0 else (255, 255, 255)))
        pdf.rect(x, y, UW, RH, style="F")
        pdf.set_font("DejaVu", "B", 9)
        max_w = LW - 4
        while pdf.get_string_width(label) > max_w and len(label) > 5:
            label = label[:-2] + "…"
        pdf.set_xy(x + 2, y); pdf.cell(LW - 2, RH, label, border=0)
        pdf.set_font("DejaVu", "", 9)
        pdf.set_xy(x + LW, y)
        pdf.cell(VW, RH, value, border=0, align="R", new_x="LMARGIN", new_y="NEXT")

    def _body(text):
        pdf.set_font("DejaVu", "", 10)
        pdf.multi_cell(UW, 6, text); pdf.ln(2)

    def _info_box(pairs):
        x, y0 = pdf.l_margin, pdf.get_y()
        pdf.set_fill_color(240, 244, 255)
        pdf.rect(x, y0, UW, len(pairs) * RH + 4, style="F")
        for lbl, val in pairs:
            pdf.set_xy(x + 2, pdf.get_y())
            pdf.set_font("DejaVu", "B", 10); pdf.cell(90, RH, lbl, border=0)
            pdf.set_font("DejaVu", "", 10)
            pdf.cell(UW - 92, RH, val, border=0, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    is_b = results["method_used"] == tl["method_hours"]

    def _pv(val, *, money=True, hours=False):
        if not val:
            return "--"
        if hours:
            return f"{float(val):.0f} h"
        return fmt_num(val, lang=lang) if money else str(val)

    # Page 1 — Disclaimer
    pdf.add_page()
    pdf.set_fill_color(200, 30, 30); pdf.set_text_color(255, 255, 255)
    pdf.set_font("DejaVu", "B", 13)
    pdf.cell(UW, 12, tl["disclaimer_label"], new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_text_color(0, 0, 0); pdf.ln(5)
    _body(tl["disclaimer_msg"])

    # Page 2 — Report
    pdf.add_page()
    pdf.set_fill_color(30, 100, 200); pdf.set_text_color(255, 255, 255)
    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(UW, 11, tl["pdf_title"], align="C", new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_text_color(0, 0, 0); pdf.ln(2)
    pdf.set_font("DejaVu", "", 9)
    pdf.cell(UW, 6, tl["pdf_generated_by"], align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(UW, 6, tl["pdf_date"].format(datetime.now().strftime("%Y-%m-%d %H:%M")),
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    _info_box([(tl["pdf_user_name"], user_name),
               (tl["pdf_used_count"], str(num_docs))])

    # Summary table — same logical order as the UI table
    _sec(tl["pdf_summary_title"])
    _hdr(tl["data_column_concept"], tl["data_column_value"])

    summary = [
        # Eligibility
        (tl["filing_status_label"],  results["filing_status"]),
        (tl["ss_check_label"],       results["ss_check"]),
        (tl["itin_check_label"],     results["itin_check"]),
        (tl["over_40_label"],        results["over_40"]),
        (tl["ot_1_5x_label"],        results["ot_1_5x"]),
        # Income
        (tl["magi_label"],           fmt_num(results["total_income"], lang=lang)),
        (tl["data_base_salary"],     fmt_num(results["base_salary"],  lang=lang)),
        # Method + inputs
        (tl["data_method_used"],     results["method_used"]),
        *([(tl["regular_rate_label"],  _pv(results["regular_rate"])),
           (tl["ot_hours_1_5_label"],  _pv(results["ot_hours_1_5"], hours=True)),
           (tl["dt_hours_2_0_label"],  _pv(results["dt_hours_2_0"], hours=True))] if is_b
          else [(tl["ot_total_1_5_paid_label"], fmt_num(results["ot_1_5_total"], lang=lang)),
                (tl["ot_total_2_0_paid_label"], fmt_num(results["ot_2_0_total"], lang=lang))]),
        # Rate verification (Option B only)
        *([(tl["data_concept_expected_rate_1_5"], fmt_num(results["expected_rate_1_5"], lang=lang)),
           (tl["data_concept_expected_rate_2_0"], fmt_num(results["expected_rate_2_0"], lang=lang)),
           (tl["actual_rate_1_5_label"],
            fmt_num(results["actual_rate_1_5"], lang=lang) if results["actual_rate_1_5"] > 0 else "--"),
           (tl["actual_rate_2_0_label"],
            fmt_num(results["actual_rate_2_0"], lang=lang) if results["actual_rate_2_0"] > 0 else "--"),
           (tl["data_rate_mismatch"], results["rate_mismatch_label"])] if is_b else []),
        # OT totals
        (tl["ot_total_1_5_paid_label"], fmt_num(results["ot_1_5_total"],  lang=lang)),
        (tl["ot_total_2_0_paid_label"], fmt_num(results["ot_2_0_total"],  lang=lang)),
        (tl["data_ot_total_paid"],       fmt_num(results["ot_total_paid"], lang=lang)),
        (tl["data_premium_1_5"],         fmt_num(results["ot_1_5_premium"], lang=lang)),
        (tl["data_premium_2_0"],
         fmt_num(results["ot_2_0_premium"], lang=lang) if results["ot_2_0_premium"] > 0 else "--"),
        # Deduction
        (tl["data_qoc_gross"],        fmt_num(results["qoc_gross"],       lang=lang)),
        (tl["phaseout_limit_label"],  fmt_num(results["deduction_limit"], lang=lang)),
        (tl["total_deduction_label"], fmt_num(results["total_deduction"], lang=lang)),
    ]
    for i, (lbl, val) in enumerate(summary):
        _row(lbl, val, idx=i)

    # Final deduction highlight
    pdf.ln(6)
    pdf.set_fill_color(0, 140, 60); pdf.set_text_color(255, 255, 255)
    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(UW, 12,
             tl["pdf_final_deduction"].format(fmt_num(results["total_deduction"], lang=lang)),
             fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0); pdf.set_font("DejaVu", "", 10)

    # Evidence
    _sec(tl["pdf_evidence_title"])
    _body(tl["pdf_docs_attached"].format(len(uploaded_files)) if uploaded_files
          else tl["pdf_no_docs"])

    # Merge attachments
    merger = PdfMerger()
    merger.append(BytesIO(pdf.output()))
    for uf in (uploaded_files or []):
        merger.append(BytesIO(uf.read()))
    out = BytesIO()
    merger.write(out); merger.close()
    return out.getvalue()

# ─────────────────────────────────────────────────────────────
# PDF SECTION
# ─────────────────────────────────────────────────────────────
if st.session_state.results:
    st.subheader(t["download_section_title"])
    user_name      = st.text_input(t["download_name_label"],
                                   placeholder=t["download_name_placeholder"],
                                   key="pdf_user_name_input")
    uploaded_files = st.file_uploader(t["download_docs_label"], type=["pdf"],
                                      accept_multiple_files=True,
                                      help=t["download_docs_help"], key="pdf_upload")
    num_docs = len(uploaded_files) if uploaded_files else 0

    col_gen, _ = st.columns([1, 3])
    with col_gen:
        if st.session_state.pdf_bytes is None:
            if st.button(t["generate_pdf"], type="primary",
                         disabled=not user_name.strip(), use_container_width=True):
                with st.spinner(t["spinner_generating_pdf"]):
                    try:
                        st.session_state.pdf_bytes = build_pdf(
                            user_name, uploaded_files, num_docs,
                            st.session_state.results, lang
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(t["error_pdf_generation"].format(e))

        if st.session_state.pdf_bytes is not None:
            st.success(t["generated_pdf_success"])
            st.info(t["generated_pdf_success_info"])
            st.download_button(
                label=t["download_button_now"],
                data=st.session_state.pdf_bytes,
                file_name=f"ZaiOT_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
                key="pdf_download_final",
            )

# ─────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(t["footer"].format(date=datetime.now().strftime("%Y-%m-%d")))