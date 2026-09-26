# ================================================================
# update_translations.ps1
# Script para automatizar la extracción, actualización y compilación
# de traducciones con Flask-Babel.
#
# Uso:
#   .\update_translations.ps1
#
# Requisitos:
#   - Python + Flask-Babel instalados
#   - babel.cfg en la raíz del proyecto
# ================================================================

Write-Host ""
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "   ORION SYSTEM - Actualización de Traducciones (i18n)" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# Configuración
# ============================================================

$BABEL_CFG = "babel.cfg"
$POT_FILE = "messages.pot"
$TRANSLATIONS_DIR = "app\translations"

# Idiomas soportados
$LANGUAGES = @("en", "pt", "fr", "de", "it", "ja", "zh")

# ============================================================
# 1. Verificar que babel.cfg existe
# ============================================================

if (-not (Test-Path $BABEL_CFG)) {
    Write-Host "❌ No se encontró '$BABEL_CFG' en la raíz del proyecto." -ForegroundColor Red
    Write-Host "   Crea el archivo con este contenido:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   [python: app/**.py]" -ForegroundColor Gray
    Write-Host "   [jinja2: app/templates/**.html]" -ForegroundColor Gray
    Write-Host "   extensions=jinja2.ext.autoescape,jinja2.ext.with_" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

# ============================================================
# 2. Verificar que pybabel está disponible
# ============================================================

try {
    $null = pybabel --version 2>&1
} catch {
    Write-Host "❌ pybabel no está instalado o no está en el PATH." -ForegroundColor Red
    Write-Host "   Instala Flask-Babel con: pip install Flask-Babel" -ForegroundColor Yellow
    exit 1
}

# ============================================================
# 3. Extraer textos
# ============================================================

Write-Host "📤 [1/3] Extrayendo textos a $POT_FILE..." -ForegroundColor Yellow
pybabel extract -F $BABEL_CFG -o $POT_FILE .

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error al extraer textos." -ForegroundColor Red
    exit 1
}
Write-Host "✅ Textos extraídos correctamente." -ForegroundColor Green
Write-Host ""

# ============================================================
# 4. Actualizar cada idioma (o inicializarlo si no existe)
# ============================================================

Write-Host "🔄 [2/3] Actualizando traducciones..." -ForegroundColor Yellow
Write-Host ""

$idiomasNuevos = @()

foreach ($lang in $LANGUAGES) {
    $poDir = Join-Path $TRANSLATIONS_DIR "$lang\LC_MESSAGES"
    $poFile = Join-Path $poDir "messages.po"

    if (Test-Path $poFile) {
        # Ya existe → actualizar
        Write-Host "   🔄 Actualizando '$lang'..." -ForegroundColor Cyan
        pybabel update -i $POT_FILE -d $TRANSLATIONS_DIR -l $lang

        if ($LASTEXITCODE -ne 0) {
            Write-Host "   ⚠️  Error actualizando '$lang'." -ForegroundColor Red
        } else {
            Write-Host "   ✅ '$lang' actualizado." -ForegroundColor Green
        }
    } else {
        # No existe → marcar para inicializar después
        $idiomasNuevos += $lang
    }
}

# ============================================================
# 5. Inicializar idiomas nuevos
# ============================================================

if ($idiomasNuevos.Count -gt 0) {
    Write-Host ""
    Write-Host "🆕 [2.5/3] Inicializando idiomas nuevos..." -ForegroundColor Yellow
    Write-Host ""

    foreach ($lang in $idiomasNuevos) {
        Write-Host "   ✨ Inicializando '$lang'..." -ForegroundColor Cyan
        pybabel init -i $POT_FILE -d $TRANSLATIONS_DIR -l $lang

        if ($LASTEXITCODE -ne 0) {
            Write-Host "   ⚠️  Error inicializando '$lang'." -ForegroundColor Red
        } else {
            Write-Host "   ✅ '$lang' inicializado. Recuerda traducir '$TRANSLATIONS_DIR\$lang\LC_MESSAGES\messages.po'." -ForegroundColor Green
        }
    }
}

Write-Host ""

# ============================================================
# 6. Compilar traducciones
# ============================================================

Write-Host "⚙️  [3/3] Compilando traducciones (.po → .mo)..." -ForegroundColor Yellow
pybabel compile -d $TRANSLATIONS_DIR

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Error al compilar traducciones." -ForegroundColor Red
    exit 1
}
Write-Host "✅ Traducciones compiladas correctamente." -ForegroundColor Green
Write-Host ""

# ============================================================
# 7. Resumen final
# ============================================================

Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "   ✅ Actualización completada" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "📁 Archivos generados/actualizados:" -ForegroundColor White
Write-Host "   - $POT_FILE" -ForegroundColor Gray
Write-Host "   - $TRANSLATIONS_DIR\<lang>\LC_MESSAGES\messages.po" -ForegroundColor Gray
Write-Host "   - $TRANSLATIONS_DIR\<lang>\LC_MESSAGES\messages.mo" -ForegroundColor Gray
Write-Host ""
Write-Host "💡 Próximos pasos:" -ForegroundColor White
Write-Host "   1. Abre los archivos .po de cada idioma y traduce los msgstr" -ForegroundColor Gray
Write-Host "   2. Vuelve a ejecutar este script para compilar los cambios" -ForegroundColor Gray
Write-Host ""
Write-Host "🌐 Idiomas soportados: $($LANGUAGES -join ', ')" -ForegroundColor White
Write-Host ""