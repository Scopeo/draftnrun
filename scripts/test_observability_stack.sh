#!/bin/bash

# =============================================================================
# Observability Stack Health Check Script
# Tests Prometheus, Tempo, Grafana, and FastAPI metrics/traces
# =============================================================================

# Configuration Variables
FASTAPI_HOST="${FASTAPI_HOST:-localhost}"
FASTAPI_PORT="${FASTAPI_PORT:-8000}"
PROMETHEUS_HOST="${PROMETHEUS_HOST:-localhost}"
PROMETHEUS_PORT="${PROMETHEUS_PORT:-9090}"
TEMPO_HOST="${TEMPO_HOST:-localhost}"
TEMPO_PORT="${TEMPO_PORT:-3200}"
GRAFANA_HOST="${GRAFANA_HOST:-localhost}"
GRAFANA_PORT="${GRAFANA_PORT:-3000}"
METRICS_PORT="${METRICS_PORT:-9100}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Emojis
CHECK="✅"
CROSS="❌"
ROCKET="🚀"
CHART="📊"
TRACE="🔍"
GEAR="⚙️"

# Helper functions
print_header() {
    echo -e "\n${BLUE}===========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}===========================================${NC}\n"
}

print_test() {
    echo -e "${YELLOW}Testing: $1${NC}"
}

print_success() {
    echo -e "${GREEN}${CHECK} $1${NC}"
}

print_error() {
    echo -e "${RED}${CROSS} $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Test functions
test_fastapi() {
    print_test "FastAPI Application"

    if curl -s "http://${FASTAPI_HOST}:${FASTAPI_PORT}/" >/dev/null; then
        print_success "FastAPI is responding"

        # Test metrics endpoint
        if curl -s "http://${FASTAPI_HOST}:${FASTAPI_PORT}/metrics" | grep -q "http_requests_total"; then
            print_success "HTTP metrics are being generated"
        else
            print_error "HTTP metrics not found"
            return 1
        fi
    else
        print_error "FastAPI is not responding"
        return 1
    fi
}

test_prometheus() {
    print_test "Prometheus Server"

    if curl -s "http://${PROMETHEUS_HOST}:${PROMETHEUS_PORT}/api/v1/targets" >/dev/null; then
        print_success "Prometheus is responding"

        # Check target health
        local targets=$(curl -s "http://${PROMETHEUS_HOST}:${PROMETHEUS_PORT}/api/v1/targets" | jq -r '.data.activeTargets[] | "\(.labels.job): \(.health)"')
        echo -e "${BLUE}Target Status:${NC}"
        echo "$targets" | while read line; do
            if [[ $line == *"up"* ]]; then
                print_success "$line"
            else
                print_error "$line"
            fi
        done
    else
        print_error "Prometheus is not responding"
        return 1
    fi
}

test_tempo() {
    print_test "Tempo Tracing Backend"

    if curl -s "http://${TEMPO_HOST}:${TEMPO_PORT}/api/echo" >/dev/null; then
        print_success "Tempo is responding"

        # Check for traces
        local trace_count=$(curl -s "http://${TEMPO_HOST}:${TEMPO_PORT}/api/search?tags=service.name=ada-backend&limit=10" | jq '.traces | length')
        if [[ $trace_count -gt 0 ]]; then
            print_success "Found $trace_count traces from ada-backend"
        else
            print_info "No traces found yet (this is normal if no requests were made)"
        fi
    else
        print_error "Tempo is not responding"
        return 1
    fi
}

test_grafana() {
    print_test "Grafana Dashboard"

    local health=$(curl -s "http://${GRAFANA_HOST}:${GRAFANA_PORT}/api/health" | jq -r '.database')
    if [[ $health == "ok" ]]; then
        local version=$(curl -s "http://${GRAFANA_HOST}:${GRAFANA_PORT}/api/health" | jq -r '.version')
        print_success "Grafana is healthy (version $version)"
    else
        print_error "Grafana is not healthy"
        return 1
    fi
}

test_metrics_integration() {
    print_test "Metrics Integration"

    print_info "Generating test requests..."
    for i in {1..5}; do
        curl -s "http://${FASTAPI_HOST}:${FASTAPI_PORT}/" >/dev/null
    done

    sleep 2 # Wait for metrics to be scraped

    # Check if metrics are available in Prometheus
    local metrics_query="http_requests_total"
    local result=$(curl -s "http://${PROMETHEUS_HOST}:${PROMETHEUS_PORT}/api/v1/query?query=${metrics_query}")
    local result_count=$(echo "$result" | jq '.data.result | length')

    if [[ $result_count -gt 0 ]]; then
        print_success "HTTP metrics are available in Prometheus"
        local sample_value=$(echo "$result" | jq -r '.data.result[0].value[1]')
        print_info "Sample metric value: $sample_value requests"
    else
        print_error "HTTP metrics not found in Prometheus"
        return 1
    fi
}

test_feature_metrics() {
    print_test "Feature Metrics Endpoint"

    if curl -s "http://${FASTAPI_HOST}:${METRICS_PORT}/metrics" | grep -q "python_info"; then
        print_success "Feature metrics endpoint is working"

        if curl -s "http://${FASTAPI_HOST}:${METRICS_PORT}/metrics" | grep -q "agent_calls_total"; then
            print_success "Agent calls metric is defined"
        else
            print_info "Agent calls metric not yet active (normal until agent is used)"
        fi
    else
        print_error "Feature metrics endpoint not responding"
        return 1
    fi
}

main() {
    print_header "${ROCKET} OBSERVABILITY STACK HEALTH CHECK"

    print_info "Testing observability stack components..."
    print_info "FastAPI: http://${FASTAPI_HOST}:${FASTAPI_PORT}"
    print_info "Prometheus: http://${PROMETHEUS_HOST}:${PROMETHEUS_PORT}"
    print_info "Tempo: http://${TEMPO_HOST}:${TEMPO_PORT}"
    print_info "Grafana: http://${GRAFANA_HOST}:${GRAFANA_PORT}"

    local failed_tests=0

    # Run all tests
    test_fastapi || ((failed_tests++))
    test_prometheus || ((failed_tests++))
    test_tempo || ((failed_tests++))
    test_grafana || ((failed_tests++))
    test_feature_metrics || ((failed_tests++))
    test_metrics_integration || ((failed_tests++))

    # Summary
    print_header "${CHART} TEST SUMMARY"

    if [[ $failed_tests -eq 0 ]]; then
        print_success "All tests passed! Observability stack is ready for stress testing"
        echo -e "\n${GREEN}${ROCKET} Ready for production monitoring!${NC}"
        echo -e "${BLUE}Access points:${NC}"
        echo -e "  ${CHART} Grafana: http://${GRAFANA_HOST}:${GRAFANA_PORT}"
        echo -e "  ${TRACE} Prometheus: http://${PROMETHEUS_HOST}:${PROMETHEUS_PORT}"
        echo -e "  ${GEAR} FastAPI Metrics: http://${FASTAPI_HOST}:${FASTAPI_PORT}/metrics"
        exit 0
    else
        print_error "$failed_tests test(s) failed"
        echo -e "\n${RED}${CROSS} Please check the failed components before proceeding${NC}"
        exit 1
    fi
}

# Check dependencies
check_dependencies() {
    local deps=("curl" "jq")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &>/dev/null; then
            print_error "Required dependency '$dep' is not installed"
            exit 1
        fi
    done
}

# Script entry point
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    check_dependencies
    main "$@"
fi
