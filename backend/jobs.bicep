// Deploy into an existing student-protected Consumption environment. Supply a
// digest-pinned private worker image and backend-only Google ADC secret separately.
param location string = resourceGroup().location
param environmentId string
param identityId string
param identityClientId string
param registryServer string
param workerImage string
param storageAccount string
param firebaseProject string
param queueName string = 'report-processing'
@secure()
param googleAdc string
@secure()
param geminiApiKey string
param geminiModel string = 'gemini-3.5-flash-lite'
param geminiFreeTierConfirmed bool = false
@minValue(1)
@maxValue(1000000000)
param storageLimitBytes int = 1000000000
param acceptNewWork bool = true

var environment = [
  { name: 'MEDIFLOW_ENV', value: 'production' }
  { name: 'MEDIFLOW_FIREBASE_PROJECT_ID', value: firebaseProject }
  { name: 'MEDIFLOW_AZURE_STORAGE_ACCOUNT_URL', value: 'https://${storageAccount}.blob.core.windows.net' }
  { name: 'MEDIFLOW_AZURE_QUEUE_NAME', value: queueName }
  { name: 'MEDIFLOW_STORAGE_LIMIT_BYTES', value: string(storageLimitBytes) }
  { name: 'MEDIFLOW_ACCEPT_NEW_WORK', value: acceptNewWork ? 'true' : 'false' }
  { name: 'AZURE_CLIENT_ID', value: identityClientId }
  { name: 'GOOGLE_APPLICATION_CREDENTIALS', value: '/secrets/google-adc.json' }
]

resource worker 'Microsoft.App/jobs@2026-07-01' = {
  name: 'report-worker'
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identityId}': {} } }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Event'
      replicaTimeout: 420
      replicaRetryLimit: 0
      secrets: [
        { name: 'google-adc', value: googleAdc }
        { name: 'gemini-api-key', value: geminiApiKey }
      ]
      registries: [{ server: registryServer, identity: identityId }]
      eventTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
        scale: {
          minExecutions: 0
          maxExecutions: 1
          pollingInterval: 30
          rules: [{
            name: 'reports'
            type: 'azure-queue'
            identity: identityId
            metadata: { accountName: storageAccount, queueName: queueName, queueLength: '1' }
          }]
        }
      }
    }
    template: {
      containers: [{
        name: 'worker'
        image: workerImage
        command: ['python', '-m', 'mediflow.worker']
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: concat(environment, [
          { name: 'MEDIFLOW_GEMINI_MODEL', value: geminiModel }
          { name: 'MEDIFLOW_GEMINI_FREE_TIER_CONFIRMED', value: geminiFreeTierConfirmed ? 'true' : 'false' }
          { name: 'GEMINI_API_KEY', secretRef: 'gemini-api-key' }
        ])
        volumeMounts: [{ volumeName: 'google', mountPath: '/secrets' }]
      }]
      volumes: [{
        name: 'google'
        storageType: 'Secret'
        secrets: [{ secretRef: 'google-adc', path: 'google-adc.json' }]
      }]
    }
  }
}

resource scheduledJobs 'Microsoft.App/jobs@2026-07-01' = [for job in [
  { name: 'report-job-reconciler', command: '--reconcile' }
  { name: 'report-retention-cleanup', command: '--maintenance' }
]: {
  name: job.name
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identityId}': {} } }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 120
      replicaRetryLimit: 0
      secrets: [{ name: 'google-adc', value: googleAdc }]
      registries: [{ server: registryServer, identity: identityId }]
      scheduleTriggerConfig: {
        cronExpression: '*/5 * * * *'
        parallelism: 1
        replicaCompletionCount: 1
      }
    }
    template: {
      containers: [{
        name: 'maintenance'
        image: workerImage
        command: ['python', '-m', 'mediflow.worker', job.command]
        resources: { cpu: json('0.25'), memory: '0.5Gi' }
        env: environment
        volumeMounts: [{ volumeName: 'google', mountPath: '/secrets' }]
      }]
      volumes: [{
        name: 'google'
        storageType: 'Secret'
        secrets: [{ secretRef: 'google-adc', path: 'google-adc.json' }]
      }]
    }
  }
}]
