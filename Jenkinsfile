pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '30'))
    timeout(time: 30, unit: 'MINUTES')
  }

  parameters {
    string(
      name: 'ITAP_IDS',
      defaultValue: 'APM0014540,APM0012058',
      description: 'Comma-separated ITAP identifiers (case-insensitive)'
    )
    string(
      name: 'MONTHS_OLD',
      defaultValue: '6',
      description: 'Branches inactive for N calendar months'
    )
    string(
      name: 'EMAIL_TO',
      defaultValue: 'vsreddy.cloudops@gmail.com',
      description: 'Notification recipients (optional)'
    )
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
          python3 --version
          echo "Runtime validation successful"
        '''
      }
    }

    stage('Run Stale Branch Scan') {
      steps {
        sh '''
          bash -euo pipefail <<'EOF'
          mkdir -p reports

          echo "======================================"
          echo "Starting Stale Branch Scan"
          echo "Organization : $GITHUB_ORG"
          echo "ITAP IDs     : $ITAP_IDS"
          echo "Months Old   : $MONTHS_OLD"
          echo "======================================"

          python3 scripts/scan_stale_branches.py \
            --org "$GITHUB_ORG" \
            --itaps "$ITAP_IDS" \
            --months "$MONTHS_OLD" \
            --out reports

          echo "Scan completed successfully."
          EOF
        '''
      }
    }
  }

  post {

    always {
      archiveArtifacts artifacts: 'reports/*', fingerprint: true, allowEmptyArchive: true
    }

    success {
      script {

        if (!fileExists('reports/stale_report.csv')) {
          echo 'No stale branches found. No email notification required.'
          return
        }

        if (!params.EMAIL_TO?.trim()) {
          echo 'EMAIL_TO not provided. Skipping email notification.'
          return
        }

        try {
          emailext(
            to: params.EMAIL_TO,
            from: 'jenkins-noreply@att.com',
            replyTo: 'devops@att.com',
            subject: "Stale GitHub Branch Audit Report – ${env.GITHUB_ORG}",
            mimeType: 'text/html',
            body: readFile('reports/email.html'),
            attachmentsPattern: 'reports/*'
          )
          echo 'Email notification sent successfully.'
        }
        catch (err) {
          echo "WARNING: Email sending failed, but pipeline will remain SUCCESS."
          echo "Error details: ${err}"
        }
      }
    }

    failure {
      echo 'Pipeline failed during scan execution.'
    }
  }
}
