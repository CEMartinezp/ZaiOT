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

st.set_page_config(
    page_title="ZaiOT - Overtime Deduction Calculator",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ─────────────────────────────────────────────────────────────
# ESTILOS GLOBALES
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
div[data-testid="stButton"] > button {
    background-color: #2ecc71 !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 0.5rem 1rem !important;
    transition: all 0.2s ease !important;
}
div[data-testid="stButton"] > button:hover {
    background-color: #27ae60 !important;
    color: white !important;
    transform: translateY(-1px);
}
div[data-testid="stButton"] > button:active {
    background-color: #219150 !important;
}
div[data-testid="stButton"] > button:disabled {
    background-color: #2ecc71 !important;
    color: white !important;
    opacity: 0.6 !important;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# TEXTOS BILINGÜES
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

        # Banner de plan activo
        "banner_single_active": "✅ Plan: Pago por uso &nbsp;|&nbsp; 1 uso disponible &nbsp;|&nbsp; Vence: {date}",
        "banner_single_used": "🔒 Plan: Pago por uso &nbsp;|&nbsp; Uso ya consumido",
        "banner_sub_active": "✅ Plan: 100 usos mensuales &nbsp;|&nbsp; {uses} usos restantes &nbsp;|&nbsp; Vence: {date}",
        "banner_sub_low": "⚠️ Plan: 100 usos mensuales &nbsp;|&nbsp; {uses} usos restantes &nbsp;|&nbsp; Vence: {date}",

        # Mensajes de estado de token
        "token_expired_single": "Tu acceso de pago por uso ha expirado.",
        "token_expired_sub": "Tu suscripción ha expirado o agotó los 100 usos.",
        "token_consumed_single": "Tu cálculo ya fue realizado. Este token de un solo uso ha sido consumido.",
        "token_consumed_sub": "Has agotado todos tus usos del mes.",
        "token_invalid": "Token no válido o no encontrado.",
        "token_buy_again_single": "Comprar nuevo acceso — $5",
        "token_buy_again_sub": "Renovar suscripción — $60/mes",
        "token_recover": "O recupera tu acceso anterior:",

        # Errores de consumo
        "consume_error": "Error al procesar tu cálculo. Intenta nuevamente.",
        "consume_expired": "Tu acceso expiró entre la validación y el cálculo. Recarga la página.",

        # Calculadora (igual que antes)
        "title": "Calculadora de Deducción por Horas Extras Calificadas (Ley OBBB 2025)",
        "desc": "Estimación de la deducción anual máxima aplicable a las horas extras calificadas (hasta $12,500 para declaración individual o $25,000 para declaración conjunta de casados).",
        "step1_title": "Paso 1: Verificación de requisitos básicos (obligatorio)",
        "step1_info": "Complete las preguntas de este paso para verificar si cumple con los requisitos básicos de elegibilidad.",
        "over_40_label": "¿Se compensan las horas trabajadas por encima de 40 semanales con pago de horas extras?",
        "ss_check_label": "¿El contribuyente posee un Número de Seguro Social (SSN) válido para trabajar?",
        "itin_check_label": "¿El contribuyente posee un Número de Identificación Tributaria Individual (ITIN)?",
        "ot_1_5x_label": "¿La mayoría de las horas extras se remuneran con una tarifa de tiempo y medio (1.5x la tarifa regular)?",
        "unlock_message": "De acuerdo con las respuestas proporcionadas, es posible que no se cumplan los requisitos para aplicar la deducción. Se recomienda consultar con un contador profesional antes de continuar.",
        "override_button": "Confirmo que cumplo los requisitos y deseo continuar",
        "eligible_blocked_info": "**Las respuestas de elegibilidad se encuentran bloqueadas.** Para modificarlas, utilice el botón inferior.",
        "eligible_auto_success": "Se verificó que se cumplen los requisitos básicos de forma automática.",
        "reiniciar_button": "🔄 Reiniciar respuestas de elegibilidad",
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
        "error_no_data": "⚠️ Debe completar al menos uno de los métodos del Paso 3.",
        "error_empty_option_a": "⚠️ La Opción A está incompleta. Complete al menos uno de los montos.",
        "error_empty_option_b": "⚠️ La Opción B está incompleta. Ingrese la tarifa regular y al menos una cantidad de horas.",
        "error_missing_total_income": "⚠️ Debe ingresar el ingreso total aproximado del año para continuar.",
        "error_income_less_than_ot": "El ingreso total reportado parece ser inferior al monto total pagado por horas extras. Revise sus respuestas.",
        "warning_no_method_chosen": "Debe seleccionar un método de ingreso de horas extras para continuar.",
        "method_hours": "Por horas trabajadas (Opción B)",
        "method_total": "Por monto total pagado (Opción A)",
        "data_tab_title": "Resumen de información ingresada",
        "data_subtitle": "Información proporcionada por el usuario",
        "data_concepts": [
            "Ingreso total aproximado del año (base + extras)",
            "Salario base estimado (ingreso total sin pago adicional por extras)",
            "Total pagado por horas extras a tiempo y medio (base + extra)",
            "Total pagado por horas extras a doble tarifa (base + extra)",
            "Total pagado por concepto de horas extras",
            "Pago adicional por horas extras a 1.5x (deducible)",
            "Pago adicional por horas extras a 2.0x (deducible)",
            "Tarifa horaria por horas extras a 1.5x",
            "Tarifa horaria por horas extras a 2.0x",
            "Límite máximo deducible según ingresos",
            "Método de cálculo utilizado",
            "¿Se compensan las horas por encima de 40 semanales con pago de horas extras?",
            "¿La mayoría de las horas extras se pagan a tiempo y medio?",
            "Estado civil para la declaración de impuestos",
            "¿Posee un Número de Seguro Social válido para trabajar?",
            "¿Posee un Número de Identificación Tributaria Individual (ITIN)?"
        ],
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
        "reduction_label": "Reducción aplicada por phase-out",
        "final_after_limit_label": "**Deducción final tras aplicar límite máximo permitido**",
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
        "generate_pdf_btn": "Generar y Descargar Reporte PDF",
        "download_error_name": "Debe ingresar el nombre completo para generar el reporte.",
        "pdf_title": "Reporte de Deducción por Horas Extras Calificadas – Ley OBBB 2025",
        "pdf_generated_by": "Hecho por ZaiOT",
        "pdf_date": "Fecha: {}",
        "pdf_user_name": "Nombre del contribuyente: {}",
        "pdf_used_count": "Cantidad de documentos adjuntos: {}",
        "pdf_summary_title": "Resumen de información ingresada",
        "pdf_results_title": "Resultados y deducción estimada",
        "pdf_evidence_title": "Documentos adjuntos como evidencia",
        "pdf_no_docs": "No se adjuntaron documentos de respaldo.",
        "pdf_docs_attached": "Se adjuntan {} documento(s) como evidencia.",
        "pdf_final_deduction": "DEDUCCIÓN FINAL ESTIMADA: {}",
        "disclaimer_label": "AVISO LEGAL Y DESCARGO DE RESPONSABILIDAD",
        "disclaimer": "**Descargo de responsabilidad:** Esta herramienta tiene únicamente fines informativos y de estimación. No constituye ni sustituye asesoría profesional en materia tributaria.",
        "disclaimer_msg": "IMPORTANTE: Esta calculadora genera estimaciones aproximadas de la deducción por horas extras calificadas conforme a la Ley OBBB 2025. No representa asesoría fiscal, legal ni contable. Los resultados son orientativos y no garantizan su aceptación por parte del IRS. Se recomienda consultar con un contador público autorizado antes de incluir cualquier deducción en una declaración de impuestos. El uso de esta herramienta es bajo exclusiva responsabilidad del usuario.",
        "language_label": "🌐 Idioma",
        "language_options": ["Español", "English"],
        "button_continue": "Continuar",
        "error_pdf_generation": "❌ Error generating PDF: {}",
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

        # Plan banner
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
        "override_button": "I confirm I meet the requirements and wish to continue",
        "eligible_blocked_info": "**Eligibility responses are currently locked.** To modify them, use the button below.",
        "eligible_auto_success": "Basic eligibility requirements have been automatically verified.",
        "reiniciar_button": "🔄 Reset eligibility responses",
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
        "error_no_data": "⚠️ You must complete at least one method in Step 3.",
        "error_empty_option_a": "⚠️ Option A is incomplete. Please enter at least one amount.",
        "error_empty_option_b": "⚠️ Option B is incomplete. Please enter the regular rate and at least one hour amount.",
        "error_missing_total_income": "⚠️ You must enter the approximate total annual income to continue.",
        "error_income_less_than_ot": "The reported total income seems to be less than the total overtime pay. Please check your answers.",
        "warning_no_method_chosen": "You must select a method for entering overtime data to continue.",
        "method_hours": "By hours worked (Option B)",
        "method_total": "By total amount paid (Option A)",
        "data_tab_title": "Summary of Entered Information",
        "data_subtitle": "Information provided by the user",
        "data_concepts": [
            "Approximate total annual income (base + overtime)",
            "Estimated base salary (total income excluding overtime premium)",
            "Total paid for time-and-a-half overtime (base + premium)",
            "Total paid for double-time overtime (base + premium)",
            "Total paid for overtime",
            "Overtime premium at 1.5x (deductible)",
            "Overtime premium at 2.0x (deductible)",
            "Hourly rate for 1.5x overtime",
            "Hourly rate for 2.0x overtime",
            "Maximum deductible limit based on income",
            "Calculation method used",
            "Are hours over 40 per week compensated with overtime pay?",
            "Are most overtime hours paid at time-and-a-half?",
            "Filing status for tax return",
            "Has a valid Social Security Number for employment?",
            "Has an Individual Taxpayer Identification Number (ITIN)?"
        ],
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
        "reduction_label": "Reduction due to phase-out",
        "final_after_limit_label": "**Final deduction after applying maximum limit**",
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
        "generate_pdf_btn": "Generate and Download PDF Report",
        "download_error_name": "Please enter your full name to generate the report.",
        "pdf_title": "Qualified Overtime Deduction Report – OBBB Act 2025",
        "pdf_generated_by": "Made by ZaiOT",
        "pdf_date": "Date: {}",
        "pdf_user_name": "Taxpayer name: {}",
        "pdf_used_count": "Number of attached documents: {}",
        "pdf_summary_title": "Summary of Entered Information",
        "pdf_results_title": "Results and Estimated Deduction",
        "pdf_evidence_title": "Supporting Documents Attached",
        "pdf_no_docs": "No supporting documents were attached.",
        "pdf_docs_attached": "{} document(s) attached as evidence.",
        "pdf_final_deduction": "FINAL ESTIMATED DEDUCTION: {}",
        "disclaimer_label": "LEGAL NOTICE AND DISCLAIMER",
        "disclaimer": "**Disclaimer:** This tool is provided for informational and estimation purposes only. It does not constitute or replace professional tax advice.",
        "disclaimer_msg": "IMPORTANT: This calculator generates approximate estimates of the qualified overtime deduction under the OBBB Act 2025. It is not tax, legal, or accounting advice. Results are for guidance only and do not guarantee acceptance by the IRS. It is strongly recommended to consult a certified public accountant before claiming any deduction. Use of this tool is at the user's sole responsibility.",
        "language_label": "🌐 Language",
        "language_options": ["Spanish", "English"],
        "button_continue": "Continue",
        "error_pdf_generation": "❌ Error al generar el PDF: {}",
    }
}

# ─────────────────────────────────────────────────────────────
# SESSION STATE — inicialización
# ─────────────────────────────────────────────────────────────
defaults = {
    "eligible_override": False,
    "results": None,
    "show_results": False,
    "pdf_generated": False,
    "completed_step_2": False,
    "completed_step_3": False,
    "pdf_bytes": None,
    "reset_eligibility": 0,
    "language": "es",
    # Token state
    "token_valid": None,       # True / False / None (no chequeado aún)
    "token_data": None,        # dict con la respuesta del worker
    "token_consumed": False,   # True si ya se consumió en esta sesión
    "token_uses_left": None,   # sincronizado tras consumo
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────
# IDIOMA
# ─────────────────────────────────────────────────────────────
current_index = 0 if st.session_state.language == "es" else 1
t = texts[st.session_state.language]

lang_selected = st.selectbox(
    t["language_label"],
    t["language_options"],
    index=current_index,
    key="global_language_selector",
)
new_language = "es" if lang_selected in ("Español", "Spanish") else "en"
if new_language != st.session_state.language:
    st.session_state.language = new_language
    st.rerun()

t = texts[st.session_state.language]
lang = st.session_state.language

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def format_number(value: float, lang: str, currency="$", decimals=2) -> str:
    if value is None:
        return f"{currency}0"
    if lang == "es":
        formatted = f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        formatted = f"{value:,.{decimals}f}"
    return f"{currency}{formatted}"

def pretty_money_input(label, value=0.0, step=100.0, decimals=2, key=None, help=None, lang="es", currency="$"):
    cols = st.columns([1.5, 3])
    with cols[0]:
        num = st.number_input(label, min_value=0.0, value=value, step=step,
                              format=f"%.{decimals}f", key=key, help=help)
    with cols[1]:
        if num == 0:
            st.metric(label=" ", value=f"{currency}0")
            return num
        if lang == "es":
            formatted = f"{num:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            formatted = f"{num:,.{decimals}f}"
        st.metric(label=" ", value=f"{currency}{formatted}")
    return num

def fmt_date(ts_ms):
    """Convierte timestamp ms → string de fecha según idioma."""
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")

# ─────────────────────────────────────────────────────────────
# TOKEN — Leer de URL y validar (solo una vez por sesión)
# ─────────────────────────────────────────────────────────────
token = st.query_params.get("token")

if token and st.session_state.token_valid is None:
    # Primera vez que vemos el token: validar contra el worker
    try:
        r = requests.get(VALIDATE_URL, params={"token": token}, timeout=8)
        data = r.json()
        if data.get("valid"):
            st.session_state.token_valid = True
            st.session_state.token_data  = data
            st.session_state.token_uses_left = data.get("uses_left")
        else:
            st.session_state.token_valid  = False
            st.session_state.token_data   = data
    except Exception:
        st.session_state.token_valid = False
        st.session_state.token_data  = {"reason": "network_error"}

# ─────────────────────────────────────────────────────────────
# LOGO
# ─────────────────────────────────────────────────────────────
st.markdown("""
<div style='text-align:center; margin-bottom:24px;'>
    <h1 style="font-size:52px;font-weight:800;letter-spacing:2px;
        background:linear-gradient(90deg,#1f6fd2,#7b61ff,#e53935);
        -webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:5px;">
        ZaiOT
    </h1>
    <p style="color:#666;font-size:15px;">OVERTIME DEDUCTION CALCULATOR</p>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# RAMA: SIN TOKEN o TOKEN INVÁLIDO → LANDING
# ─────────────────────────────────────────────────────────────
def show_landing(reason=None):
    """Muestra la página de compra. reason puede ser expired/consumed/invalid."""
    t_l = texts[st.session_state.language]

    # Mensaje de estado si viene de token inválido/expirado
    if reason == "expired":
        token_type = st.session_state.token_data.get("type", "single") if st.session_state.token_data else "single"
        msg = t_l["token_expired_sub"] if token_type == "sub" else t_l["token_expired_single"]
        st.error(msg)
    elif reason == "consumed":
        token_type = st.session_state.token_data.get("type", "single") if st.session_state.token_data else "single"
        msg = t_l["token_consumed_sub"] if token_type == "sub" else t_l["token_consumed_single"]
        st.warning(msg)
    elif reason == "invalid":
        st.error(t_l["token_invalid"])

    # Título landing
    st.markdown(f"<h2 style='text-align:center;margin-bottom:4px;'>{t_l['landing_title']}</h2>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center;color:#666;margin-bottom:32px;'>{t_l['landing_subtitle']}</p>", unsafe_allow_html=True)
    st.caption(t_l["landing_disclaimer"])
    st.markdown("---")

    # ── Tarjetas de planes ──
    col_single, col_sub = st.columns(2, gap="large")

    # CSS adaptativo — usa variables CSS que responden al tema de Streamlit
    st.markdown("""
    <style>
    /* Tema claro */
    @media (prefers-color-scheme: light) {
        .plan-card-text   { color: #1a1a2e !important; }
        .plan-card-sub    { color: #555 !important; }
        .plan-card-li     { color: #444 !important; }
    }
    /* Tema oscuro */
    @media (prefers-color-scheme: dark) {
        .plan-card-text   { color: #f0f0f0 !important; }
        .plan-card-sub    { color: #aaa !important; }
        .plan-card-li     { color: #ccc !important; }
    }
    /* Fallback por si Streamlit sobreescribe — usa currentColor */
    .plan-card-name-single { color: #4da6ff !important; }
    .plan-card-name-sub    { color: #a78bfa !important; }
    </style>
    """, unsafe_allow_html=True)

    with col_single:
        features_html = ''.join(f'<li class="plan-card-li">{f}</li>' for f in t_l['plan_single_features'])
        st.markdown(f"""
        <div style="border:2px solid #1f6fd2;border-radius:12px;padding:28px 24px;text-align:center;height:100%;">
            <h3 class="plan-card-name-single" style="margin-bottom:4px;">{t_l['plan_single_name']}</h3>
            <p class="plan-card-text" style="font-size:36px;font-weight:800;margin:8px 0;">{t_l['plan_single_price']}</p>
            <p class="plan-card-sub" style="font-size:14px;margin-bottom:20px;">{t_l['plan_single_desc']}</p>
            <ul style="text-align:left;font-size:14px;line-height:2;padding-left:20px;margin-bottom:24px;">
                {features_html}
            </ul>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(f'<div style="text-align:center;margin-top:16px;"><a href="{STRIPE_SINGLE}" target="_blank" style="display:inline-block;background:#27ae60;color:#fff;text-decoration:none;padding:14px 36px;border-radius:10px;font-size:16px;font-weight:700;box-shadow:0 4px 14px rgba(39,174,96,0.35);">{t_l["btn_buy_single"]}</a></div>', unsafe_allow_html=True)

    with col_sub:
        features_html_sub = ''.join(f'<li class="plan-card-li">{f}</li>' for f in t_l['plan_sub_features'])
        st.markdown(f"""
        <div style="border:2px solid #7b61ff;border-radius:12px;padding:28px 24px;text-align:center;height:100%;position:relative;">
            <div style="position:absolute;top:-12px;left:50%;transform:translateX(-50%);background:#7b61ff;color:#fff;font-size:11px;font-weight:700;padding:4px 14px;border-radius:20px;letter-spacing:1px;">POPULAR</div>
            <h3 class="plan-card-name-sub" style="margin-bottom:4px;">{t_l['plan_sub_name']}</h3>
            <p class="plan-card-text" style="font-size:36px;font-weight:800;margin:8px 0;">{t_l['plan_sub_price']}</p>
            <p class="plan-card-sub" style="font-size:14px;margin-bottom:20px;">{t_l['plan_sub_desc']}</p>
            <ul style="text-align:left;font-size:14px;line-height:2;padding-left:20px;margin-bottom:24px;">
                {features_html_sub}
            </ul>
        </div>
        """, unsafe_allow_html=True)
        st.markdown(f'<div style="text-align:center;margin-top:16px;"><a href="{STRIPE_SUB}" target="_blank" style="display:inline-block;background:#7b61ff;color:#fff;text-decoration:none;padding:14px 36px;border-radius:10px;font-size:16px;font-weight:700;box-shadow:0 4px 14px rgba(123,97,255,0.35);">{t_l["btn_buy_sub"]}</a></div>', unsafe_allow_html=True)

    st.markdown("---")

    # ── Sección reenvío de acceso ──
    st.markdown(f"<h4 style='text-align:center;'>{t_l['resend_title']}</h4>", unsafe_allow_html=True)

    col_email, col_btn = st.columns([3, 1])
    with col_email:
        resend_email = st.text_input(
            label="email_resend",
            placeholder=t_l["resend_placeholder"],
            label_visibility="collapsed",
            key="resend_email_input"
        )
    with col_btn:
        if st.button(t_l["resend_btn"], use_container_width=True):
            if not resend_email or "@" not in resend_email:
                st.error(t_l["resend_error"])
            else:
                with st.spinner(t_l["resend_sending"]):
                    try:
                        requests.post(RESEND_URL, json={"email": resend_email}, timeout=8)
                    except Exception:
                        pass  # Silencioso — no revelar nada
                st.success(t_l["resend_success"])

# ─────────────────────────────────────────────────────────────
# DECIDIR QUÉ MOSTRAR
# ─────────────────────────────────────────────────────────────

# Sin token en URL
if not token:
    show_landing()
    st.stop()

# Token en URL pero inválido
if st.session_state.token_valid is False:
    reason = st.session_state.token_data.get("reason", "invalid") if st.session_state.token_data else "invalid"
    if reason in ("expired",):
        show_landing(reason="expired")
    elif reason in ("consumed",):
        show_landing(reason="consumed")
    else:
        show_landing(reason="invalid")
    st.stop()

# Token válido — mostrar banner y calculadora
token_data = st.session_state.token_data

# ─────────────────────────────────────────────────────────────
# BANNER DE PLAN ACTIVO
# ─────────────────────────────────────────────────────────────
def show_plan_banner():
    td = st.session_state.token_data
    if not td:
        return

    plan_type  = td.get("type", "single")
    expires_at = td.get("expires_at")
    uses_left  = st.session_state.token_uses_left  # sincronizado tras consumo
    exp_date   = fmt_date(expires_at) if expires_at else "—"

    if plan_type == "single":
        if st.session_state.token_consumed:
            # Ya consumido en esta sesión — mostramos como informativo
            html = f"<div style='background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:10px 18px;margin-bottom:16px;font-size:14px;'>{t['banner_single_used']}</div>"
        else:
            html = f"<div style='background:#d4edda;border:1px solid #28a745;border-radius:8px;padding:10px 18px;margin-bottom:16px;font-size:14px;'>{t['banner_single_active'].format(date=exp_date)}</div>"
    else:
        uses = uses_left if uses_left is not None else "?"
        color_bg  = "#fff3cd" if isinstance(uses, int) and uses <= 10 else "#d4edda"
        color_brd = "#ffc107" if isinstance(uses, int) and uses <= 10 else "#28a745"
        tpl = t["banner_sub_low"] if isinstance(uses, int) and uses <= 10 else t["banner_sub_active"]
        html = f"<div style='background:{color_bg};border:1px solid {color_brd};border-radius:8px;padding:10px 18px;margin-bottom:16px;font-size:14px;'>{tpl.format(uses=uses, date=exp_date)}</div>"

    st.markdown(html, unsafe_allow_html=True)

show_plan_banner()

# ─────────────────────────────────────────────────────────────
# CALCULADORA — exactamente igual que el código original
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
# PASO 1: ELEGIBILIDAD
# ─────────────────────────────────────────────────────────────
eligible = st.session_state.eligible_override

with st.expander(f"### {t['step1_title']}", expanded=not eligible):
    st.info(t["step1_info"])

    filing_status = st.radio(
        t["filing_status_label"], t["filing_status_options"],
        index=None, horizontal=True, disabled=eligible,
        key=f"filing_status_radio_{st.session_state.reset_eligibility}"
    )
    over_40 = st.radio(
        t["over_40_label"], t["answer_options"],
        index=None, horizontal=True, disabled=eligible, help=t["over_40_help"],
        key=f"over_40_radio_{st.session_state.reset_eligibility}"
    )
    ot_1_5x = st.radio(
        t["ot_1_5x_label"], t["answer_options"],
        index=None, horizontal=True, disabled=eligible, help=t["ot_1_5x_help"],
        key=f"ot_1_5x_radio_{st.session_state.reset_eligibility}"
    )
    ss_check = st.radio(
        t["ss_check_label"], t["answer_options"],
        index=None, horizontal=True, disabled=eligible, help=t["ss_check_help"],
        key=f"ss_check_radio_{st.session_state.reset_eligibility}"
    )
    itin_check = st.radio(
        t["itin_check_label"], t["answer_options"],
        index=None, horizontal=True, disabled=eligible, help=t["itin_check_help"],
        key=f"itin_check_radio_{st.session_state.reset_eligibility}"
    )

    partial_responses = any(x is None for x in [filing_status, over_40, ot_1_5x, ss_check, itin_check])

    auto_eligible = (
        filing_status != t["filing_status_options"][3] and
        over_40   == t["answer_options"][0] and
        ot_1_5x   == t["answer_options"][0] and
        ss_check  == t["answer_options"][0] and
        itin_check == t["answer_options"][1]
    )

    eligible = auto_eligible or st.session_state.eligible_override

    if eligible:
        if st.session_state.eligible_override:
            st.info(t["eligible_blocked_info"])
        else:
            st.session_state.eligible_override = True
            st.rerun()

        if st.button(t["reiniciar_button"], type="secondary", use_container_width=True):
            st.session_state.eligible_override = False
            st.session_state.reset_eligibility += 1
            st.rerun()

    elif not partial_responses:
        st.warning(t["unlock_message"])
        if st.button(t["override_button"], use_container_width=True, type="secondary"):
            st.session_state.eligible_override = True
            st.rerun()

# ─────────────────────────────────────────────────────────────
# PASO 2: INGRESOS
# ─────────────────────────────────────────────────────────────
if eligible:
    with st.expander(f"### {t['step2_title']}", expanded=True):
        st.info(t["step2_info"])

        total_income = pretty_money_input(
            t["magi_label"], value=0.0, step=1000.0, decimals=2, lang=lang
        )

        if not st.session_state.completed_step_2:
            if st.button(t["button_continue"], type="secondary", use_container_width=True):
                if total_income <= 0:
                    st.error(t["error_missing_total_income"])
                else:
                    st.session_state.completed_step_2 = True
                    st.rerun()

        if st.session_state.completed_step_2:
            st.success(t["step2_completed_msg"])

        if not st.session_state.completed_step_2:
            st.stop()

    # ─────────────────────────────────────────────────────────
    # PASO 3: MÉTODO DE HORAS EXTRAS
    # ─────────────────────────────────────────────────────────
    with st.expander(f"### {t['step3_title']}", expanded=True):
        ot_1_5_total = ot_2_0_total = regular_rate = ot_hours_1_5 = dt_hours_2_0 = 0.0
        rate_1_5 = rate_2_0 = 0.0

        st.info(t["step3_info"])

        method_choice = st.radio(
            t["choose_method_label"], t["choose_method_options"],
            index=None, horizontal=True
        )

        if not method_choice:
            st.warning(t["warning_no_method_chosen"])
            st.stop()

        elif method_choice == t["choose_method_options"][0]:
            with st.expander(t["option_a_title"], expanded=True):
                ot_1_5_total = pretty_money_input(
                    t["ot_total_1_5_paid_label"], value=0.0, step=100.0, decimals=2,
                    help=t["ot_total_1_5_paid_help"], lang=lang
                )
                ot_2_0_total = pretty_money_input(
                    t["ot_total_2_0_paid_label"], value=0.0, step=100.0, decimals=2,
                    help=t["ot_total_2_0_paid_help"], lang=lang
                )
        else:
            with st.expander(t["option_b_title"], expanded=True):
                regular_rate = pretty_money_input(
                    t["regular_rate_label"], value=0.0, step=0.5, decimals=2,
                    help=t["regular_rate_help"]
                )
                ot_hours_1_5 = pretty_money_input(
                    t["ot_hours_1_5_label"], value=0.0, step=5.0, decimals=2,
                    help=t["ot_hours_1_5_help"], lang=lang, currency=" "
                )
                dt_hours_2_0 = pretty_money_input(
                    t["dt_hours_2_0_label"], value=0.0, step=5.0, decimals=2,
                    help=t["dt_hours_2_0_help"], lang=lang, currency=" "
                )

    # ─────────────────────────────────────────────────────────
    # BOTÓN CALCULAR — consume token si todo está bien
    # ─────────────────────────────────────────────────────────
    if st.button(t["calculate_button"], type="secondary", use_container_width=True):

        # ── Validaciones ──
        if total_income <= 0:
            st.error(t["error_missing_total_income"])
            st.stop()

        if method_choice == t["choose_method_options"][0]:
            if not (ot_1_5_total > 0 or ot_2_0_total > 0):
                st.error(t["error_empty_option_a"])
                st.stop()
            method_used = t["method_total"]
            rate_1_5 = rate_2_0 = 0.0
        else:
            if not (regular_rate > 0 and (ot_hours_1_5 + dt_hours_2_0) > 0):
                st.error(t["error_empty_option_b"])
                st.stop()
            method_used = t["method_hours"]
            rate_1_5 = regular_rate * 1.5
            rate_2_0 = regular_rate * 2.0
            ot_1_5_total = ot_hours_1_5 * rate_1_5
            ot_2_0_total = dt_hours_2_0 * rate_2_0

        # ── Cálculo ──
        ot_total_paid  = ot_1_5_total + ot_2_0_total
        ot_1_5_premium = calculate_ot_premium(ot_1_5_total, 1.5, "total")
        ot_2_0_premium = calculate_ot_premium(ot_2_0_total, 2.0, "total")
        qoc_gross      = ot_1_5_premium + ot_2_0_premium

        if filing_status == t["filing_status_options"][2]:
            max_ded, phase_start, phase_range = 25000, 300000, 250000
        else:
            max_ded, phase_start, phase_range = 12500, 150000, 125000

        deduction_limit = apply_phaseout(magi=total_income, max_value=max_ded,
                                         phase_start=phase_start, phase_range=phase_range)
        total_deduction = min(qoc_gross, deduction_limit)
        base_salary     = total_income - ot_total_paid

        if base_salary < 0:
            st.error(t["error_income_less_than_ot"])
            st.stop()

        # ── CONSUMIR TOKEN (solo si aún no se consumió en esta sesión) ──
        if not st.session_state.token_consumed:
            try:
                rc = requests.post(CONSUME_URL, json={"token": token}, timeout=8)
                rc_data = rc.json()

                if not rc_data.get("success"):
                    reason = rc_data.get("reason", "error")
                    if reason in ("expired",):
                        st.error(t["consume_expired"])
                    else:
                        st.error(t["consume_error"])
                    st.stop()

                # Consumo exitoso — actualizar estado
                st.session_state.token_consumed   = True
                st.session_state.token_uses_left  = rc_data.get("uses_left")  # None para single

            except Exception:
                st.error(t["consume_error"])
                st.stop()

        # ── Guardar resultados y mostrar ──
        st.session_state.results = {
            "total_income":   total_income,
            "base_salary":    base_salary,
            "ot_total_paid":  ot_total_paid,
            "ot_1_5_total":   ot_1_5_total,
            "ot_2_0_total":   ot_2_0_total,
            "ot_1_5_premium": ot_1_5_premium,
            "ot_2_0_premium": ot_2_0_premium,
            "rate_1_5":       rate_1_5,
            "rate_2_0":       rate_2_0,
            "method_used":    method_used,
            "over_40":        "--" if not over_40    else over_40,
            "ot_1_5x":        "--" if not ot_1_5x   else ot_1_5x,
            "ss_check":       "--" if not ss_check   else ss_check,
            "filing_status":  "--" if not filing_status else filing_status,
            "itin_check":     "--" if not itin_check else itin_check,
            "qoc_gross":      qoc_gross,
            "deduction_limit": deduction_limit,
            "total_deduction": total_deduction,
        }
        st.session_state.show_results = True
        st.rerun()  # rerun para actualizar el banner inmediatamente

# ─────────────────────────────────────────────────────────────
# RESULTADOS
# ─────────────────────────────────────────────────────────────
if eligible and st.session_state.show_results:
    tab_results, tab_data = st.tabs([t["results_tab_title"], t["data_tab_title"]])

    with tab_results:
        st.subheader(t["results_title"])
        data            = st.session_state.results
        qoc_gross       = data["qoc_gross"]
        deduction_limit = data["deduction_limit"]
        total_deduction = data["total_deduction"]

        if qoc_gross <= deduction_limit:
            st.success(t["total_deduction_no_limit"].format(format_number(total_deduction, lang)))
        else:
            st.warning(t["total_deduction_with_limit"].format(format_number(total_deduction, lang)))
            st.info(t["limit_info"].format(
                f"\\{format_number(qoc_gross, lang)}",
                f"\\{format_number(deduction_limit, lang)}"
            ))

        st.markdown("---")
        col_left_res, col_right_res = st.columns([1, 2])

        with col_left_res:
            st.metric(
                label=t["total_deduction_label"],
                value=format_number(total_deduction, lang),
                delta=t["total_deduction_delta"]
            )
            st.success(t["total_deduction_success"])

        with col_right_res:
            st.subheader(t["breakdown_subtitle"])
            st.metric(t["qoc_gross_label"],       format_number(qoc_gross, lang))
            st.metric(t["phaseout_limit_label"],  format_number(deduction_limit, lang))
            st.metric(t["final_after_limit_label"], format_number(total_deduction, lang))

    with tab_data:
        st.subheader(t["data_subtitle"])
        data = st.session_state.results
        data_summary = {
            t["data_column_concept"]: t["data_concepts"],
            t["data_column_value"]: [
                format_number(data["total_income"],    lang),
                format_number(data["base_salary"],     lang),
                format_number(data["ot_1_5_total"],    lang),
                "--" if not data["ot_2_0_total"]   else format_number(data["ot_2_0_total"],   lang),
                format_number(data["ot_total_paid"],   lang),
                format_number(data["ot_1_5_premium"],  lang),
                "--" if not data["ot_2_0_premium"] else format_number(data["ot_2_0_premium"], lang),
                "--" if not data["rate_1_5"]        else format_number(data["rate_1_5"],        lang),
                "--" if not data["rate_2_0"]        else format_number(data["rate_2_0"],        lang),
                format_number(data["deduction_limit"], lang),
                data["method_used"],
                data["over_40"],
                data["ot_1_5x"],
                data["filing_status"],
                data["ss_check"],
                data["itin_check"],
            ]
        }
        st.dataframe(pd.DataFrame(data_summary), use_container_width=True)

# ─────────────────────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────────────────────
def build_final_pdf(user_name, uploaded_files, num_docs, results, lang):
    import os
    BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
    font_reg   = os.path.join(BASE_DIR, "fonts", "DejaVuSans.ttf")
    font_bold  = os.path.join(BASE_DIR, "fonts", "DejaVuSans-Bold.ttf")

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(20, 20, 20)
    pdf.add_font("DejaVu", "",  font_reg)
    pdf.add_font("DejaVu", "B", font_bold)
    pdf.set_font("DejaVu", "", 11)

    USABLE_W = 170
    LABEL_W  = 120
    VALUE_W  = 50
    ROW_H    = 7
    ALT_COLOR = (245, 245, 245)
    INDENT   = 2

    def section_title(text):
        pdf.ln(8)
        pdf.set_fill_color(30, 100, 200)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_x(pdf.l_margin + INDENT)
        pdf.cell(USABLE_W - INDENT, 9, text, new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("DejaVu", "", 11)
        pdf.ln(2)

    def table_row(label, value, row_index=0):
        x, y = pdf.get_x(), pdf.get_y()
        avg_cw = pdf.get_string_width("a")
        cpl = int((LABEL_W - INDENT) / max(avg_cw, 1))
        lines_needed = max(1, -(-len(label) // cpl))
        row_height = max(ROW_H, lines_needed * ROW_H)
        pdf.set_fill_color(*(ALT_COLOR if row_index % 2 == 0 else (255, 255, 255)))
        pdf.rect(x, y, USABLE_W, row_height, style="F")
        pdf.set_font("DejaVu", "B", 10)
        pdf.set_xy(x + INDENT, y)
        pdf.multi_cell(LABEL_W - INDENT, ROW_H, label, border=0)
        pdf.set_font("DejaVu", "", 10)
        pdf.set_xy(x + LABEL_W, y)
        pdf.multi_cell(VALUE_W, ROW_H, value, border=0, align="R")
        pdf.set_xy(x, y + row_height)

    def header_row(col1, col2):
        pdf.set_fill_color(50, 50, 50)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("DejaVu", "B", 10)
        x, y = pdf.get_x(), pdf.get_y()
        pdf.set_xy(x + INDENT, y)
        pdf.multi_cell(LABEL_W - INDENT, ROW_H + 1, col1, fill=True, border=0)
        pdf.set_xy(x + LABEL_W, y)
        pdf.multi_cell(VALUE_W, ROW_H + 1, col2, fill=True, border=0, align="R",
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("DejaVu", "", 10)

    def body_text(text, size=10):
        pdf.set_font("DejaVu", "", size)
        pdf.multi_cell(USABLE_W, 6, text)
        pdf.ln(2)

    def kv_simple(label, value, label_w=70):
        x, y = pdf.get_x(), pdf.get_y()
        pdf.set_font("DejaVu", "B", 11)
        pdf.multi_cell(label_w, 7, label, border=0)
        y_after = pdf.get_y()
        pdf.set_xy(x + label_w, y)
        pdf.set_font("DejaVu", "", 11)
        pdf.multi_cell(USABLE_W - label_w, 7, value, border=0)
        pdf.set_y(max(y_after, pdf.get_y()))

    # PAGE 1 — DISCLAIMER
    pdf.add_page()
    pdf.set_fill_color(200, 30, 30)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("DejaVu", "B", 14)
    pdf.set_x(pdf.l_margin + INDENT)
    pdf.cell(USABLE_W - INDENT, 12, t["disclaimer_label"], new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(6)
    body_text(t["disclaimer_msg"])

    # PAGE 2 — REPORT
    pdf.add_page()
    pdf.set_fill_color(30, 100, 200)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("DejaVu", "B", 15)
    pdf.multi_cell(USABLE_W, 11, t["pdf_title"], align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(USABLE_W, 6, t["pdf_generated_by"], align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(USABLE_W, 6, t["pdf_date"].format(datetime.now().strftime("%Y-%m-%d %H:%M")),
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    info_y = pdf.get_y()
    pdf.set_font("DejaVu", "B", 11)
    kv_simple(t["pdf_user_name"].replace("{}", "").strip(),  user_name)
    kv_simple(t["pdf_used_count"].replace("{}", "").strip(), str(num_docs))
    info_bottom = pdf.get_y()
    pdf.set_y(info_y)
    pdf.set_fill_color(240, 244, 255)
    pdf.rect(pdf.get_x(), info_y, USABLE_W, info_bottom - info_y + 3, style="F")
    kv_simple(t["pdf_user_name"].replace("{}", "").strip(),  user_name)
    kv_simple(t["pdf_used_count"].replace("{}", "").strip(), str(num_docs))
    pdf.ln(4)

    section_title(t["pdf_summary_title"])
    header_row(t["data_column_concept"], t["data_column_value"])

    summary_items = [
        (t["data_concepts"][0],  format_number(results["total_income"],    lang=lang)),
        (t["data_concepts"][1],  format_number(results["base_salary"],     lang=lang)),
        (t["data_concepts"][2],  format_number(results["ot_1_5_total"],    lang=lang)),
        (t["data_concepts"][3],  format_number(results["ot_2_0_total"],    lang=lang)),
        (t["data_concepts"][4],  format_number(results["ot_total_paid"],   lang=lang)),
        (t["data_concepts"][5],  format_number(results["ot_1_5_premium"],  lang=lang)),
        (t["data_concepts"][6],  format_number(results["ot_2_0_premium"],  lang=lang)),
        (t["data_concepts"][7],  format_number(results["rate_1_5"],        lang=lang)),
        (t["data_concepts"][8],  format_number(results["rate_2_0"],        lang=lang)),
        (t["data_concepts"][9],  format_number(results["deduction_limit"], lang=lang)),
        (t["data_concepts"][10], results["method_used"]),
        (t["data_concepts"][11], results["over_40"]),
        (t["data_concepts"][12], results["ot_1_5x"]),
        (t["data_concepts"][13], results["filing_status"]),
        (t["data_concepts"][14], results["ss_check"]),
        (t["data_concepts"][15], results["itin_check"]),
    ]
    for i, (label, value) in enumerate(summary_items):
        table_row(label, value, row_index=i)

    section_title(t["pdf_results_title"])
    header_row(t["data_column_concept"], t["data_column_value"])
    results_items = [
        (t["qoc_gross_label"],       format_number(results["qoc_gross"],       lang=lang)),
        (t["phaseout_limit_label"],  format_number(results["deduction_limit"], lang=lang)),
        (t["total_deduction_label"], format_number(results["total_deduction"], lang=lang)),
    ]
    for i, (lbl, val) in enumerate(results_items):
        table_row(lbl, val, row_index=i)

    pdf.ln(8)
    pdf.set_fill_color(0, 140, 60)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("DejaVu", "B", 13)
    pdf.set_x(pdf.l_margin + INDENT)
    pdf.multi_cell(USABLE_W - INDENT, 13,
                   t["pdf_final_deduction"].format(format_number(results["total_deduction"], lang=lang)),
                   fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("DejaVu", "", 11)

    section_title(t["pdf_evidence_title"])
    if uploaded_files:
        body_text(t["pdf_docs_attached"].format(len(uploaded_files)))
    else:
        body_text(t["pdf_no_docs"])

    pdf_bytes = pdf.output()
    merger = PdfMerger()
    merger.append(BytesIO(pdf_bytes))
    if uploaded_files:
        for uf in uploaded_files:
            merger.append(BytesIO(uf.read()))
    final_io = BytesIO()
    merger.write(final_io)
    merger.close()
    return final_io.getvalue()

# ─────────────────────────────────────────────────────────────
# SECCIÓN PDF — solo si hay resultados
# ─────────────────────────────────────────────────────────────
if eligible and st.session_state.results:
    st.subheader(t["download_section_title"])

    user_name = st.text_input(
        t["download_name_label"],
        placeholder=t["download_name_placeholder"],
        key="pdf_user_name_input"
    )
    uploaded_files = st.file_uploader(
        t["download_docs_label"], type=["pdf"],
        accept_multiple_files=True, help=t["download_docs_help"], key="pdf_upload"
    )
    num_docs = len(uploaded_files) if uploaded_files else 0

    col_gen, _ = st.columns([1, 3])
    with col_gen:
        if st.session_state.pdf_bytes is None:
            if st.button(t["generate_pdf"], type="primary",
                         disabled=not user_name.strip(), use_container_width=True):
                with st.spinner(t["spinner_generating_pdf"]):
                    try:
                        pdf_bytes = build_final_pdf(
                            user_name=user_name, uploaded_files=uploaded_files,
                            num_docs=num_docs, results=st.session_state.results,
                            lang=lang
                        )
                        st.session_state.pdf_bytes = pdf_bytes
                        st.rerun()
                    except Exception as e:
                        st.error(t["error_pdf_generation"].format(str(e)))

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
                key="pdf_download_final"
            )

# ─────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(t["footer"].format(date=datetime.now().strftime("%Y-%m-%d")))
