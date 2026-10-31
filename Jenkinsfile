pipeline {
    agent any

    stages {
        stage('Obtener codigo') {
            steps {
                checkout scm
            }
        }

        stage('Construir imagen Docker') {
            steps {
                sh 'docker build -t orion-ecommerce:${BUILD_NUMBER} .'
            }
        }

        stage('Validar sintaxis Python') {
            steps {
                sh 'docker run --rm orion-ecommerce:${BUILD_NUMBER} python -m compileall -q app'
            }
        }

        stage('Resultado') {
            steps {
                echo 'La imagen Docker se construyo y la sintaxis de Python se valido correctamente.'
            }
        }
    }
}
