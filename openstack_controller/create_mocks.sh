#!/opt/homebrew/bin/bash

create_file() {
  # Assign the parameters to variables
  dir_path=$1
  file_name=$2
  content=$3

  # Create the full file path by concatenating the directory path and file name
  file_path="$dir_path/$file_name"

  # Check if the directory exists, and create it if it doesn't
  if [ ! -d $dir_path ]; then
    mkdir -p $dir_path
  fi

  # Check if the file exists, and create it if it doesn't
  if [ ! -f $file_path ]; then
    touch $file_path
  fi

  # Write the content to the file
  echo "$content" > $file_path
}

process_endpoint() {
  declare -A named_args=()
  for arg in "$@"; do
      case "$arg" in
          --*=*) named_args[${arg%%=*}]=${arg#*=};;
          *) echo "Unknown argument: $arg"; exit 1;;
      esac
  done

  # Assign the parameters to variables
  method="${named_args["--method"]:-"GET"}"
  endpoint="${named_args["--endpoint"]:-"/"}"
  port="${named_args["--port"]:-80}"
  file_name="${named_args["--file_name"]:-"$method.json"}"
  data="${named_args["--data"]:-""}"

  printf "\033[32m%-6s\033[0m $method $endpoint [$data]\n" "INFO"

  local response=$(curl -D headers -s --request "$method" -H "$nova_microversion_header" -H "$ironic_microversion_header" -H "X-Auth-Token: $x_auth_token" -H "Content-Type: application/json" --data "$data" "http://$os_ip:$port$endpoint")
  http_status_code=$(cat "headers" | awk '/^HTTP/ {print $2}' | dos2unix)
  auth_token=$(cat "headers" | awk '/X-Subject-Token/ {print $2}' | dos2unix)
  if [ -n "$auth_token" ]; then
    printf "\033[32m%-6s\033[0m X-Subject-Token: %s\n" "INFO" "$auth_token"
    x_auth_token=$auth_token
  fi
  if [[ "$http_status_code" -ge 200 && "$http_status_code" -lt 400 ]]; then
    printf "\033[32m%-6s\033[0m Creating file %s%s/%s\n" "INFO" "$root_folder" "$endpoint" "$file_name"
    response=$(echo "$response" | jq)
    create_file "$root_folder$endpoint" "$file_name" "$response"
    export RESPONSE="$response"
    return 0
  else
    printf "\033[31m%-6s\033[0m %s for endpoint %s\n" "ERROR" "$http_status_code" "$endpoint"
    return 1
  fi
}

os_ip=$(gcloud compute instances describe "$1" --format='get(networkInterfaces[0].accessConfigs[0].natIP)' --project "datadog-integrations-lab" --zone "europe-west4-a")
root_folder="tests/fixtures/"$1"/nova-${2:-"default"}-ironic-${3:-"default"}"

nova_microversion_header=""
ironic_microversion_header=""
if [ $# -eq 2 ]
  then
    nova_microversion_header="X-OpenStack-Nova-API-Version: $2"
fi
if [ $# -eq 3 ]
  then
    nova_microversion_header="X-OpenStack-Nova-API-Version: $2"
    ironic_microversion_header="X-OpenStack-Ironic-API-Version: $3"
fi
x_auth_token=""
echo "$nova_microversion_header"
echo "$ironic_microversion_header"

data=$(echo "{'auth': {'identity': {'methods': ['password'], 'password': {'user': {'name': 'admin', 'domain': { 'id': 'default' }, 'password': 'password'}}}}}" | sed "s/'/\"/g")
process_endpoint --method="POST" --endpoint="/identity/v3/auth/tokens" --file_name="unscoped.json" --data="$data"
data=$(echo "{'auth': {'identity': {'methods': ['password'], 'password': {'user': {'name': 'admin', 'domain': { 'id': 'default' }, 'password': 'password'}}}, 'scope': {'domain': {'id': 'default' }}}}" | sed "s/'/\"/g")
process_endpoint --method="POST" --endpoint="/identity/v3/auth/tokens" --file_name="domain_default.json" --data="$data"
# Component endpoints
process_endpoint --endpoint="/identity/v3"
process_endpoint --endpoint="/compute/v2.1"
process_endpoint --endpoint="/volume/v3/"
process_endpoint --port=9696 --endpoint="/networking/"
process_endpoint --endpoint="/baremetal"
process_endpoint --endpoint="/load-balancer"
# Keystone
process_endpoint --endpoint="/identity/v3/domains"
process_endpoint --endpoint="/identity/v3/projects"
process_endpoint --endpoint="/identity/v3/users"
process_endpoint --endpoint="/identity/v3/groups"
for group_id in $(echo "$RESPONSE" | jq -r '.groups[]' | jq -r '.id'); do
  printf "\033[32m%-6s\033[0m Group id: %s\n" "INFO" "$group_id"
  process_endpoint --endpoint="/identity/v3/groups/$group_id/users"
done
process_endpoint --endpoint="/identity/v3/services"
process_endpoint --endpoint="/identity/v3/registered_limits"
process_endpoint --endpoint="/identity/v3/limits"
# Nova
process_endpoint --endpoint="/identity/v3/auth/projects"
for project_id in $(echo "$RESPONSE" | jq -r '.projects[]' | jq -r '.id'); do
  printf "\033[32m%-6s\033[0m Project id: %s\n" "INFO" "$project_id"
  data=$(echo "{'auth': {'identity': {'methods': ['password'], 'password': {'user': {'name': 'admin', 'domain': { 'id': 'default' }, 'password': 'password'}}}, 'scope': {'project': {'id': '$project_id'}}}}" | sed "s/'/\"/g")
  process_endpoint --method="POST" --endpoint="/identity/v3/auth/tokens" --file_name="project_$project_id.json" --data="$data"
  process_endpoint --endpoint="/compute/v2.1/limits?tenant_id=$project_id"
  process_endpoint --endpoint="/compute/v2.1/os-quota-sets/$project_id"
  process_endpoint --endpoint="/compute/v2.1/servers/detail?project_id=$project_id"

  for server_id in $(echo "$RESPONSE" | jq -r '.servers[]' | jq -r '.id'); do
    process_endpoint --endpoint="/compute/v2.1/servers/$server_id/diagnostics"
  done
  process_endpoint --port=9696 --endpoint="/networking/v2.0/quotas/$project_id"
done
process_endpoint --endpoint="/compute/v2.1/os-aggregates"
process_endpoint --endpoint="/compute/v2.1/os-hypervisors/detail?with_servers=true"
num_uptime=$(echo "$RESPONSE" | jq -r '.hypervisors[] | select(.uptime != null) | length')
if [[ $num_uptime -eq 0 ]]; then
  for hypervisor_id in $(echo "$RESPONSE" | jq -r '.hypervisors[]' | jq -r '.id'); do
    process_endpoint --endpoint="/compute/v2.1//os-hypervisors/$hypervisor_id/uptime"
  done
fi
process_endpoint --endpoint="/compute/v2.1/flavors/detail"
for flavor_id in $(echo "$RESPONSE" | jq -r '.flavors[]' | jq -r '.id'); do
  process_endpoint --endpoint="/compute/v2.1/flavors/$flavor_id"
done

# Ironic
process_endpoint --endpoint="/baremetal/nodes?detail=True"
process_endpoint --endpoint="/baremetal/nodes/detail"
process_endpoint --endpoint="/baremetal/conductors"

# Octavia
process_endpoint --endpoint="/load-balancer/v2/lbaas/loadbalancers"
for loadbalancer_id in $(echo "$RESPONSE" | jq -r '.loadbalancers[]' | jq -r '.id'); do
  process_endpoint --endpoint="/load-balancer/v2/lbaas/loadbalancers/$loadbalancer_id/stats/"
done

process_endpoint --endpoint="/load-balancer/v2/lbaas/listeners"
for listener_id in $(echo "$RESPONSE" | jq -r '.listeners[]' | jq -r '.id'); do
  process_endpoint --endpoint="/load-balancer/v2/lbaas/listeners/$listener_id/stats/"
done

process_endpoint --endpoint="/load-balancer/v2/lbaas/pools"
for pool_id in $(echo "$RESPONSE" | jq -r '.pools[]' | jq -r '.id'); do
  process_endpoint --endpoint="/load-balancer/v2/lbaas/pools/$pool_id/members/"
done

process_endpoint --endpoint="/load-balancer/v2/lbaas/healthmonitors"

process_endpoint --endpoint="/load-balancer/v2/octavia/amphorae"
for amphora_id in $(echo "$RESPONSE" | jq -r '.amphorae[]' | jq -r '.id'); do
  process_endpoint --endpoint="/load-balancer/v2/octavia/amphorae/$amphora_id/stats/"
done

rm headers