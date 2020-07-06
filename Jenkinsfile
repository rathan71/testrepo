def secrets = [
    [$class: 'VaultSecret', path:
'secret/jenkins/966fd541-137d-4da4-b71d-40562cd46ef2', secretValues: [
        [$class: 'VaultSecretValue', envVar: 'ARTIFACTORY_API_KEY', vaultKey: 'value']]],
]

pipeline {
  agent any
  options {
    disableConcurrentBuilds()
  }
  triggers {
    cron('H H * * 7')
  }
  parameters {
    string(name: 'BRANCH_NAME', defaultValue: 'master', description: '')
  }
  stages {
    stage('Artifactory cleanup') {
      steps {
        script {
          timestamps {
            ws("workspace/infrastructure-scripts-${env.EXECUTOR_NUMBER}") {
              checkout([$class: 'GitSCM',
                        branches: [[name: "$BRANCH_NAME"]],
                        doGenerateSubmoduleConfigurations: false,
                        extensions: [[$class: 'CleanBeforeCheckout'],
                                     [$class: 'CloneOption', depth: 0, noTags: false]],
                        submoduleCfg: [],
                        userRemoteConfigs: [[credentialsId: 'github-infra',
                                             url: 'git@github.com:Addepar/infrastructure-scripts.git']]])
              // using account artifactorycleanup on jfrog
              // account password is in vault under key 09429b5e-9f0f-4639-a79a-83437d1fefc1
              wrap([$class: 'VaultBuildWrapper', vaultSecrets: secrets]) {
                sh 'python artifactory-cleanup/cleanup_artifactory.py 270 30'
              }
            }
          }
        }
      }
    }
  }
}
