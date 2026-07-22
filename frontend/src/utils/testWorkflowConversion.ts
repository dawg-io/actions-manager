import { yamlToGui, guiToYaml } from '../utils/workflowGuiConversion';

// Sample YAML workflow for testing
const sampleYaml = `name: CI Pipeline
on: 
  push:
    branches: [main, develop]
  pull_request:
    types: [opened, synchronize]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v5
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install dependencies
        run: npm install
  test:
    runs-on: ubuntu-latest
    needs: [build]
    steps:
      - name: Checkout
        uses: actions/checkout@v5
      - name: Run tests
        run: npm test`;

// Test conversion functions
export function testWorkflowConversion() {
  console.log('🧪 Testing YAML ⇄ GUI conversion...');
  
  try {
    // Test YAML to GUI conversion
    console.log('📄 Original YAML:');
    console.log(sampleYaml);
    
    const gui = yamlToGui(sampleYaml);
    console.log('📝 Converted to GUI:');
    console.log(JSON.stringify(gui, null, 2));
    
    // Test GUI to YAML conversion
    const convertedYaml = guiToYaml(gui);
    console.log('📄 Converted back to YAML:');
    console.log(convertedYaml);
    
    // Test round-trip
    const guiRoundTrip = yamlToGui(convertedYaml);
    console.log('🔄 Round-trip GUI:');
    console.log(JSON.stringify(guiRoundTrip, null, 2));
    
    console.log('✅ Conversion test completed successfully!');
    return true;
    
  } catch (error) {
    console.error('❌ Conversion test failed:', error);
    return false;
  }
}

// Run test if this file is executed directly
if (typeof window !== 'undefined') {
  // Browser environment - can be called from console
  (window as any).testWorkflowConversion = testWorkflowConversion;
}