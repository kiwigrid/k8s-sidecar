# Definiert das Haupt-Target für den Multi-Arch-Build
target "k8s-sidecar" {
  platforms = [
    "linux/amd64",
    "linux/arm64",
    "linux/arm/v7",
    "linux/riscv64"
  ]
  # Tags are dynamically defined in wokflows, so we leave this empty here
  tags = []
}
group "default" {
  targets = ["k8s-sidecar"]
}
