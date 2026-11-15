// Uso: notificarResultado()  — normalmente en post { always { ... } }
def call() {
    String duracion = currentBuild.durationString.replace(' and counting', '')
    echo """
================ RESUMEN DEL BUILD ================
Job:        ${env.JOB_NAME}
Build:      #${env.BUILD_NUMBER}
Rama:       ${env.BRANCH_NAME ?: 'n/a'}
Commit:     ${env.GIT_SHORT ?: 'n/a'}
Imagen:     ${env.IMAGE_TAG ?: 'no construida'}
Resultado:  ${currentBuild.currentResult}
Duración:   ${duracion}
Detalle:    ${env.BUILD_URL}
===================================================
"""
}
