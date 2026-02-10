pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '30'))
  }

  parameters {
    string(name: 'ITAP_IDS', defaultValue: 'APM0014540,APM0012058')
    string(name: 'MONTHS_OLD', defaultValue: '6')
    string(name: 'EMAIL_TO', defaultValue: 'vsreddy.cloudops@gmail.com')
  }

  environment {
    GITHUB_ORG   = 'ATT-TEST-GA'
    GITHUB_TOKEN = credentials('github-pat')
    TZ = 'UTC'
  }

  stages {

    stage('Clean Workspace') {
      steps {
        deleteDir()
      }
    }

    stage('Checkout Source') {
      steps {
        checkout scm
      }
    }

    stage('Validate Runtime') {
      steps {
        sh '''
          bash -lc '
            set -e
            python3 --version
            python3 - <<EOF
print("Runtime validation successful")
EOF
          '
        '''
      }
    }

    stage('Run Stale Branch Scan') {
      steps {
        sh '''
          bash -lc '
            set -euo pipefail
            mkdir -p reports

            python3 scripts/scan_stale_branches.py \
              --org "$GITHUB_ORG" \
              --itaps "$ITAP_IDS" \
              --months "$MONTHS_OLD" \
              --out reports
          '
        '''
      }
    }
  }

  post {
    always {
      archiveArtifacts artifacts: 'reports/*', fingerprint: true
    }

    success {
      script {
        if (!fileExists('reports/stale_report.csv')) {
          echo 'No stale branches found. Email not sent.'
          return
        }

        emailext(
          to: params.EMAIL_TO,
          subject: "Stale GitHub Branch Report – ${env.GITHUB_ORG}",
          mimeType: 'text/html',
          body: readFile('reports/email.html'),
          attachmentsPattern: 'reports/*'
        )
      }
    }
  }
}
