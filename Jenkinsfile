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
          set -e
          python3 --version
          python3 - <<EOF
print("Runtime validation successful")
EOF
        '''
      }
    }

    stage('Run Stale Branch Scan') {
      steps {
        sh '''
          bash -lc '
            set -euo pipefail
            mkdir -p reports

            # Convert ITAP IDs to uppercase (case-insensitive handling)
            NORMALIZED_ITAPS=$(echo "$ITAP_IDS" | tr "[:lower:]" "[:upper:]")

            echo "Using ITAP IDs: $NORMALIZED_ITAPS"

            python3 scripts/scan_stale_branches.py \
              --org "$GITHUB_ORG" \
              --itaps "$NORMALIZED_ITAPS" \
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
          echo 'No stale branches found. No email notification sent.'
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
          echo "Email sending failed, but build will NOT fail."
          echo "Error: ${err}"
        }
      }
    }
  }
}
