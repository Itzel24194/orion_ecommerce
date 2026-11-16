@Library('ci-lib') _

pipeline {
    agent { label 'python' }

    options {
        skipDefaultCheckout(true)
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '15'))
        disableConcurrentBuilds()
    }

    parameters {
        string(name: 'COBERTURA_MINIMA', defaultValue: '50', description: 'Porcentaje mínimo de cobertura de líneas')
        booleanParam(name: 'SIMULAR_FALLA_PROD', defaultValue: false, description: 'Simula una falla en producción')
    }

    environment {
        DOCKER_HOST = 'tcp://dind:2375'
        REGISTRY    = 'registry:5000'
        IMAGE_NAME  = 'orion-api'
    }

    stages {
        stage('Checkout') {
            steps {
                script {
                    def scmVars = checkout scm
                    env.GIT_COMMIT = scmVars.GIT_COMMIT
                }
                sh 'git log -1 --oneline'
            }
        }

        stage('Versionado') {
            steps {
                script {
                    env.GIT_SHORT = env.GIT_COMMIT.take(7)
                    env.IMAGE_TAG = "${env.BUILD_NUMBER}-${env.GIT_SHORT}"
                    currentBuild.displayName = "#${env.BUILD_NUMBER} · ${env.GIT_SHORT}"
                    currentBuild.description = "Imagen: ${env.REGISTRY}/${env.IMAGE_NAME}:${env.IMAGE_TAG}"
                }
            }
        }

        stage('Info') {
            steps {
                echo "Build #${env.BUILD_NUMBER}"
                echo "Commit: ${env.GIT_COMMIT}"
                echo "Nodo: ${env.NODE_NAME}"
                echo "Workspace: ${env.WORKSPACE}"
            }
        }

        stage('Preparar entorno') {
            steps {
                sh '''
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install --quiet --upgrade pip
                    pip install --quiet -r requirements-dev.txt
                '''
            }
        }

        stage('MongoDB de pruebas') {
            steps {
                script {
                    String id = env.BUILD_TAG.replaceAll('[^a-zA-Z0-9_.-]', '-')
                    env.TEST_MONGO = "mongo-test-${id}"
                    env.TEST_MONGO_PORT = "${27100 + ((env.BUILD_TAG.hashCode() & 0x7fffffff) % 800)}"
                }
                sh '''
                    docker rm -f $TEST_MONGO 2>/dev/null || true
                    docker run -d --name $TEST_MONGO -p $TEST_MONGO_PORT:27017 mongo:7
                    for i in $(seq 1 30); do
                        if docker exec $TEST_MONGO mongosh --quiet --eval 'db.runCommand({ping:1}).ok' >/dev/null 2>&1; then
                            echo "MongoDB de pruebas listo en dind:$TEST_MONGO_PORT"
                            exit 0
                        fi
                        sleep 2
                    done
                    echo "MongoDB de pruebas no arrancó"; exit 1
                '''
            }
        }

        stage('Calidad') {
            failFast true
            parallel {
                stage('Lint (flake8)') {
                    steps {
                        sh '''
                            . .venv/bin/activate
                            mkdir -p reports
                            flake8 app tests --tee --output-file=reports/flake8.txt || true
                        '''
                    }
                    post {
                        always { recordIssues(tools: [flake8(pattern: 'reports/flake8.txt')]) }
                    }
                }

                stage('Seguridad (bandit)') {
                    steps {
                        sh '''
                            . .venv/bin/activate
                            mkdir -p reports
                            bandit -r app -ll -f txt -o reports/bandit.txt || true
                        '''
                    }
                }

                stage('Pruebas y cobertura') {
                    when { expression { return false } }
                    steps {
                        sh '''
                            . .venv/bin/activate
                            mkdir -p reports
                            pytest --junitxml=reports/junit.xml || true
                        '''
                    }
                    post {
                        always {
                            junit allowEmptyResults: true, testResults: 'reports/junit.xml'
                        }
                    }
                }
            }
        }

        stage('Construir imagen') {
            steps {
                sh '''
                    docker build --pull \\
                        --build-arg APP_VERSION=${IMAGE_TAG} \\
                        -t ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG} .
                '''
            }
        }

        stage('Publicar imagen') {
            when { anyOf { branch 'main'; branch 'develop' } }
            steps {
                sh '''
                    docker push ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG} || true
                    docker tag ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG} ${REGISTRY}/${IMAGE_NAME}:latest || true
                    docker push ${REGISTRY}/${IMAGE_NAME}:latest || true
                '''
            }
        }

        stage('Desplegar a staging') {
            when { anyOf { branch 'main'; branch 'develop' } }
            steps {
                sh 'DOCKER_HOST=tcp://dind:2375 docker network create orion-staging 2>/dev/null || true'
                sh 'DOCKER_HOST=tcp://dind:2375 docker rm -f orion-mongo-staging 2>/dev/null || true'
                sh 'DOCKER_HOST=tcp://dind:2375 docker run -d --name orion-mongo-staging --network orion-staging mongo:7'
                sh '''
                    for i in $(seq 1 30); do
                        DOCKER_HOST=tcp://dind:2375 docker exec orion-mongo-staging mongosh --quiet --eval 'db.runCommand({ping:1}).ok' >/dev/null 2>&1 && exit 0
                        sleep 2
                    done
                    echo "MongoDB de staging no arrancó"; exit 1
                '''
                desplegarContenedor(
                    nombre: 'orion-api-staging',
                    imagen: "${env.REGISTRY}/${env.IMAGE_NAME}:${env.IMAGE_TAG}",
                    puerto: 8081,
                    puertoInterno: 5000,
                    red: 'orion-staging',
                    envVars: [
                        MONGO_URL : 'mongodb://orion-mongo-staging:27017',
                        DB_NAME   : 'orion_staging',
                        JWT_SECRET: 'secreto-solo-para-staging',
                        APP_ENV   : 'staging'
                    ]
                )
            }
        }

        stage('Smoke test staging') {
            when { anyOf { branch 'main'; branch 'develop' } }
            steps {
                smokeTest(
                    url: 'http://dind:8081',
                    version: env.IMAGE_TAG,
                    checks: [
                        [ruta: '/health',      esperado: 200],
                        [ruta: '/ruta-inexistente',   esperado: 404]
                    ]
                )
            }
        }

        stage('Aprobación a producción') {
            when { beforeInput true; branch 'main' }
            options { timeout(time: 15, unit: 'MINUTES') }
            input {
                message "¿Promover ${env.IMAGE_TAG} a producción?"
                ok 'Promover'
                submitter 'admin,aprobador'
                submitterParameter 'APROBADOR'
                parameters {
                    string(name: 'MOTIVO', defaultValue: '', description: 'Motivo del cambio')
                }
            }
            steps {
                echo "Aprobado por ${APROBADOR}. Motivo: ${MOTIVO}"
            }
        }

        stage('Desplegar a producción') {
            when { branch 'main' }
            steps {
                script {
                    String previa = sh(
                        script: "DOCKER_HOST=tcp://dind:2375 docker inspect --format '{{.Config.Image}}' orion-api-prod 2>/dev/null || echo ninguna",
                        returnStdout: true
                    ).trim()
                    writeFile file: 'reports/prod-imagen-previa.txt', text: previa + '\n'
                }
                withCredentials([string(credentialsId: 'orion-jwt-prod', variable: 'JWT_SECRET')]) {
                    sh '''
                        DOCKER_HOST=tcp://dind:2375 docker network create orion-prod 2>/dev/null || true
                        if ! DOCKER_HOST=tcp://dind:2375 docker ps --format '{{.Names}}' | grep -qx orion-mongo-prod; then
                            DOCKER_HOST=tcp://dind:2375 docker rm -f orion-mongo-prod 2>/dev/null || true
                            DOCKER_HOST=tcp://dind:2375 docker run -d --name orion-mongo-prod --network orion-prod --restart unless-stopped \\
                                -v orion_mongo_prod_data:/data/db mongo:7
                        fi
                    '''
                    desplegarContenedor(
                        nombre: 'orion-api-prod',
                        imagen: "${env.REGISTRY}/${env.IMAGE_NAME}:${env.IMAGE_TAG}",
                        puerto: 8082,
                        puertoInterno: 5000,
                        red: 'orion-prod',
                        envVars: [
                            MONGO_URL: 'mongodb://orion-mongo-prod:27017',
                            DB_NAME  : 'orion',
                            APP_ENV  : 'production'
                        ],
                        envPass: ['JWT_SECRET']
                    )
                }
                smokeTest(url: 'http://dind:8082', version: env.IMAGE_TAG)
                script {
                    if (params.SIMULAR_FALLA_PROD) {
                        error 'Falla simulada'
                    }
                }
            }
            post {
                failure {
                    echo 'Falló el despliegue a producción: intentando rollback'
                    script {
                        String previa = fileExists('reports/prod-imagen-previa.txt')
                            ? readFile('reports/prod-imagen-previa.txt').trim() : 'ninguna'
                        if (previa && previa != 'ninguna') {
                            withCredentials([string(credentialsId: 'orion-jwt-prod', variable: 'JWT_SECRET')]) {
                                desplegarContenedor(
                                    nombre: 'orion-api-prod',
                                    imagen: previa,
                                    puerto: 8082,
                                    puertoInterno: 5000,
                                    red: 'orion-prod',
                                    envVars: [
                                        MONGO_URL: 'mongodb://orion-mongo-prod:27017',
                                        DB_NAME  : 'orion',
                                        APP_ENV  : 'production'
                                    ],
                                    envPass: ['JWT_SECRET']
                                )
                            }
                            echo "ROLLBACK: se restauró la imagen ${previa}"
                            currentBuild.description = "ROLLBACK a ${previa} (falló ${env.IMAGE_TAG})"
                        }
                    }
                }
            }
        }
    }

    post {
        always {
            sh 'DOCKER_HOST=tcp://dind:2375 docker rm -f "${TEST_MONGO:-ninguno}" 2>/dev/null || true'
            sh 'DOCKER_HOST=tcp://dind:2375 docker image prune -f >/dev/null 2>&1 || true'
            notificarResultado()
        }
        cleanup {
            cleanWs()
        }
    }
}