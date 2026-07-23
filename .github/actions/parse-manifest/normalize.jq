# Normalizes the merged manifest so Terraform always sees a uniform shape:
# every app has an explicit containers map and (unless "none") a full ingress
# object; single-container shorthand fields fold into containers.main.

def container_defaults: {"cpu": 0.5, "memory": "1Gi", "env": {}, "secrets": []};

def fold_shorthand:
  if has("containers") then .containers
  else
    {"main": (
        (if .cpu     != null then {"cpu": .cpu}         else {} end)
      + (if .memory  != null then {"memory": .memory}   else {} end)
      + (if .docker  != null then {"docker": .docker}   else {} end)
      + (if .image   != null then {"image": .image}     else {} end)
      + (if .env     != null then {"env": .env}         else {} end)
      + (if .secrets != null then {"secrets": .secrets} else {} end)
    )}
  end;

def norm_ingress:
  . as $app
  | ($app.port // 8080) as $port
  | {"external": false, "target_port": $port, "transport": "auto", "allow_insecure": false} as $defaults
  | $app.ingress
  | if . == "none" then null
    elif . == null or . == "internal" then $defaults
    elif . == "public" then $defaults + {"external": true}
    else $defaults + .
    end;

def norm_app:
  . as $app
  | (fold_shorthand | map_values(container_defaults + .)) as $containers
  | ($app | norm_ingress) as $ingress
  | (if $app.name != null then {"name": $app.name} else {} end)
    + (if $ingress != null then {"ingress": $ingress} else {} end)
    + {"replicas": ({"min": 1, "max": 3} + ($app.replicas // {}))}
    + {"containers": $containers};

if .app != null and .apps != null then
  error("manifest mixes singular app with apps (possibly via an environment overlay); use one form")
else . end
| if .app != null then .apps = {"main": .app} | del(.app) else . end
| if .apps != null then .apps |= map_values(norm_app) else . end
