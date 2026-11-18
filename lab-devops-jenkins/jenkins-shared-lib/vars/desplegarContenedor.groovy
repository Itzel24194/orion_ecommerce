// Uso:
//   desplegarContenedor(nombre: 'orion-api-staging',
//                       imagen: 'registry:5000/orion-api:14-a3f9c2d',
//                       puerto: 8081,                 // puerto publicado en dind
//                       puertoInterno: 5000,          // opcional (Flask = 5000)
//                       red: 'orion-staging',         // opcional
//                       envVars: [DB_NAME: 'orion'],  // opcional (valores NO secretos)
//                       envPass: ['JWT_SECRET'])      // opcional (secretos ya exportados por withCredentials)
def call(Map cfg = [:]) {
    ['nombre', 'imagen', 'puerto'].each { k ->
        if (!cfg[k]) {
            error "desplegarContenedor: falta el parámetro '${k}'"
        }
    }
    int interno = (cfg.puertoInterno ?: 5000) as int
    List flags = []

    if (cfg.red) {
        flags << "--network ${cfg.red}"
    }
    if (cfg.envVars) {
        for (String k : cfg.envVars.keySet()) {
            flags << "-e ${k}='${cfg.envVars[k]}'"
        }
    }
    if (cfg.envPass) {
        for (String k : cfg.envPass) {
            flags << "-e ${k}"
        }
    }

    sh """
        DOCKER_HOST=tcp://dind:2375 docker rm -f ${cfg.nombre} 2>/dev/null || true
        DOCKER_HOST=tcp://dind:2375 docker run -d --name ${cfg.nombre} --restart unless-stopped ${flags.join(' ')} \\
            -p ${cfg.puerto}:${interno} ${cfg.imagen}
    """
    echo "Contenedor ${cfg.nombre} desplegado con ${cfg.imagen} en el puerto ${cfg.puerto}"
}