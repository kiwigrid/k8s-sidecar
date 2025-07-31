
%if 0%{?with_debug}
# https://bugzilla.redhat.com/show_bug.cgi?id=995136#c12
%global _dwz_low_mem_die_limit 0
%else
%global debug_package   %{nil}
%endif
%define __os_install_post %{nil}

%global _name k8s-sidecar
%global _buildhost build-ol%{?oraclelinux}-%{?_arch}.oracle.com

Name:           %{_name}
Version:        1.30.7
Release:        1%{?dist}
Summary:        This is a docker container intended to run inside a kubernetes cluster to collect config maps with a specified label and store the included files in a local folder.
License:        MIT
Vendor:		    Oracle America
Group:          System/Management
Url:            https://github.com/kiwigrid/k8s-sidecar
Source:         %{name}-%{version}.tar.bz2
BuildRequires:  python3
BuildRequires:  python3-pip
BuildRequires:  gcc

%description
This is a docker container intended to run inside a kubernetes cluster to collect config maps with a specified label and store the included files in an local folder.
It can also send an HTTP request to a specified URL after a configmap change. The main target is to be run as a sidecar container to supply an application with information from the cluster.
The contained Python script is working from Kubernetes API 1.10.

%prep
%setup -q -n %{name}-%{version}

%build
cd src
python3 -m pip install -r requirements.txt

%install
install -m 755 -d %{buildroot}/usr/local/share/olcne/%{name}/
cp -a %{_builddir}/%{name}-%{version}/* %{buildroot}/usr/local/share/olcne/%{name}/

%files
%license LICENSE SECURITY.md THIRD_PARTY_LICENSES.txt
/usr/local/share/olcne/%{name}/

%changelog
* Mon Jul 21 2025 Olcne-Builder Jenkins <olcne-builder_us@oracle.com> - 1.30.7-1
- Added Oracle Specific Build Files for k8s-sidecar
