#
# This python script is to test CoprHD services for VxRack. It takes the following actions sequentially
#
#  1. Retrieve Catalog ID using name
#  2. Retrieve Service IDs using names
#  3. Add sds node to an existing ScaleIO cluster
#  4. Remove that node from the cluster
#
# This script requires: 
#
#  1. ScaleIO cluster to already be installed
#  2. SVM of new node to be deployed (configured with networking)
#  3. CoprHD to have been initialized with coprhd-init.py
#

import requests
import logging
logging.captureWarnings(True)
import sys
import time
# validate arguments
if len(sys.argv) < 2:
    print "Usage: coprhd-service-test.py <CoprHD Virtual IP>"
    exit(1)

VIP=sys.argv[1]
PASSWORD = "ChangeMe"

URI = "https://%s:4443" % VIP
SERVICE_URI = "https://%s:443" % VIP
HEADER_AUTH_TOKEN = "X-SDS-AUTH-TOKEN"
HEADER_CONTENT_TYPE = "Content-Type"
HEADER_ACCEPT = "ACCEPT"

SERVICE_NAME_ADD_NODE = "VxRackAddnewScaleIOnode"
SERVICE_NAME_REMOVE_NODE = "VxRackRemoveScaleIOnode"
CATALOG_CATEGORY_NAME = "VCE VxRack System Services"

def login():
    url = URI + "/login";
    resp = requests.get(url, verify=False, auth=('root', PASSWORD));
    if (resp.status_code != 200):
        print("Fail to login CoprHD %s " % VIP)
        resp.raise_for_status()
    return resp.headers[HEADER_AUTH_TOKEN];

def checkClusterState():
    url = URI + "/upgrade/cluster-state";
    headers = {HEADER_AUTH_TOKEN: loginToken, HEADER_ACCEPT: "application/json"};
    resp = requests.get(url, verify = False, headers = headers);
    resp.raise_for_status()
    json = resp.json()
    return json["cluster_state"]

def orderRemoveNodeService(serviceId):
    url = SERVICE_URI + "/api/services/%s" % serviceId;
    headers = {HEADER_AUTH_TOKEN: loginToken,
           HEADER_CONTENT_TYPE: "application/x-www-form-urlencoded",
           HEADER_ACCEPT: "application/json"};
    data = {
        "scaleio_interface":"eth0",
        "scaleio_volume_name":"empty",
        "mdm_hosts":"[{'ip':'1.1.1.50','user':'root','pass':'admin'},{'ip':'1.1.1.51','user':'root','pass':'admin'},{'ip':'1.1.1.52','user':'root','pass':'admin'}]",
        "sds_hosts":"[{'ip':'1.1.1.54','user':'root','pass':'admin'}]",
        "sdc_hosts":"[]"
    }
    resp = requests.post(url, verify = False, headers = headers, data = data);
    resp.raise_for_status();
    json = resp.json();
    return json["id"];

def orderAddNodeService(serviceId):
    url = SERVICE_URI + "/api/services/%s" % serviceId;
    headers = {HEADER_AUTH_TOKEN: loginToken,
           HEADER_CONTENT_TYPE: "application/x-www-form-urlencoded",
           HEADER_ACCEPT: "application/json"};
    data = {
        "scaleio_common_file_install_file_location":"/data/scaleio",
        "scaleio_interface":"eth0",
        "scaleio_sds_disks":"{'ansible_available_disks':['/dev/sdb']}",
        "scaleio_protection_domain":"protection_domain1",
        "scaleio_storage_pool":"pool1",
        "mdm_hosts":"[{'ip':'1.1.1.50','user':'root','pass':'admin'},{'ip':'1.1.1.51','user':'root','pass':'admin'},{'ip':'1.1.1.52','user':'root','pass':'admin'}]",
        "sds_hosts":"[{'ip':'1.1.1.54','user':'root','pass':'admin'}]"
    }
    resp = requests.post(url, verify = False, headers = headers, data = data);
    resp.raise_for_status();
    json = resp.json();
    return json["id"];

def waitForOrder(orderId):
    for i in range(0,1000):
        url = SERVICE_URI + "/api/orders/%s" % orderId;
        headers = {HEADER_AUTH_TOKEN: loginToken, "ACCEPT": "application/json"};
        resp = requests.get(url, verify = False, headers = headers);
        resp.raise_for_status()
        json = resp.json();
        if (json["status"] == "PENDING") or (json["status"] == "EXECUTING"):
            time.sleep(60)
        elif json["status"] == "ERROR":
            raise ValueError('The Order Failed',json["message"])
        elif json["status"] == "SUCCESS":
            return
        else:
            raise ValueError('Order returned an unexpected status',json["status"],json["message"])
    raise ValueError('Timeout occured while waiting for order to finish')


def getRootTenantId():
    url = URI + "/tenant";
    headers = {HEADER_AUTH_TOKEN: loginToken, "ACCEPT": "application/json"};
    resp = requests.get(url, verify = False, headers = headers);
    resp.raise_for_status()
    json = resp.json();
    return json["id"];

def getRootCategoryId(rootTenantId):
    url = URI + "/catalog/categories?tenantId=%s" % rootTenantId;
    headers = {HEADER_AUTH_TOKEN: loginToken, "ACCEPT": "application/json"};
    resp = requests.get(url, verify = False, headers = headers);
    resp.raise_for_status()
    json = resp.json();
    return json["id"];

def getVxRackCategory(rootCategoryId, categoryName):
    url = URI + "/catalog/categories/%s/categories" % rootCategoryId;
    headers = {HEADER_AUTH_TOKEN: loginToken, HEADER_ACCEPT: "application/json"};
    resp = requests.get(url, verify = False, headers = headers);
    resp.raise_for_status()
    json = resp.json()
    for category in json["catalog_category"]:
        if category["name"] == categoryName:
            return category["id"];

def getCategoryService(categoryId,serviceName):
    url = URI + "/catalog/categories/%s/services" % categoryId;
    headers = {HEADER_AUTH_TOKEN: loginToken, HEADER_ACCEPT: "application/json"};
    resp = requests.get(url, verify = False, headers = headers);
    resp.raise_for_status()
    json = resp.json()
    for service in json["catalog_service"]:
        if service["name"] == serviceName:
            return service["id"];

loginToken = login();
state = checkClusterState();
if state != "STABLE":
    print "CoprHD cluster state is not stable %s. Please try again later" % state;
    exit(1);

print "CoprHD %s Cluster state is stable." % VIP
print "Start CoprHD VxRack testing ..."
print

rootTenantId = getRootTenantId();
rootCategoryId = getRootCategoryId(rootTenantId);
print "Root tenant ID: %s" % rootTenantId
print "Root catalog category ID: %s" % rootCategoryId
print

print "Get service IDs ..."
categoryId = getVxRackCategory(rootCategoryId, CATALOG_CATEGORY_NAME);
addID = getCategoryService(categoryId,SERVICE_NAME_ADD_NODE);
removeId = getCategoryService(categoryId,SERVICE_NAME_REMOVE_NODE);
print "Add scaleIO node service  ID: %s" % addID
print "Remove scaleIO node service  ID: %s" % removeId
print "Done"
print

print "Order Add Node service ..."
addOrderID = orderAddNodeService(addID);
print "Add ScaleIO node order ID: %s" % addOrderID
print "Waiting for order to complete ..."
waitForOrder(addOrderID);
print "Order Completed Successfully"
print

print "Order Remove Node service ..."
removeOrderID = orderRemoveNodeService(removeId);
print "Remove ScaleIO node order ID: %s" % removeOrderID
print "Waiting for order to complete ..."
waitForOrder(removeOrderID);
print "Order Completed Successfully"
print

print "CoprHD VxRack testing is done successfully."
