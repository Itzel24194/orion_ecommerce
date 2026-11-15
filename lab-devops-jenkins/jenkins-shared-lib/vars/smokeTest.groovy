// Uso:
//   smokeTest(url: 'http://dind:8081', version: env.IMAGE_TAG, minutos: 2,
//             checks: [[ruta: '/api/products/', esperado: 200],
//                      [ruta: '/ruta-inexistente', esperado: 404]])
def call(Map cfg = [:]) {
    if (!cfg.url) {
        error 'smokeTest: falta el parámetro url'
    }
    int minutos = (cfg.minutos ?: 2) as int

    timeout(time: minutos, unit: 'MINUTES') {
        waitUntil(initialRecurrencePeriod: 3000) {
            return sh(script: "curl -fsS ${cfg.url}/health", returnStatus: true) == 0
        }
    }

    String body = sh(script: "curl -fsS ${cfg.url}/health", returnStdout: true).trim()
    echo "1) /health responde: ${body}"

    if (cfg.version) {
        if (!body.contains(cfg.version.toString())) {
            error "smokeTest: se esperaba la versión ${cfg.version} y /health devolvió: ${body}"
        }
        echo "2) Es la versión correcta: ${cfg.version}"
    }

    List checks = cfg.checks ?: []
    int n = 3
    for (c in checks) {
        String metodo = c.metodo ?: 'GET'
        String codigo = sh(
            script: "curl -sL -o /dev/null -w '%{http_code}' -X ${metodo} ${cfg.url}${c.ruta}",
            returnStdout: true
        ).trim()
        if (codigo != "${c.esperado}") {
            error "smokeTest: ${metodo} ${c.ruta} devolvió ${codigo}, se esperaba ${c.esperado}"
        }
        echo "${n}) ${metodo} ${c.ruta} -> ${codigo} OK"
        n++
    }
    echo "Smoke test OK en ${cfg.url}"
}
