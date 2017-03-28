#
# This python script is to initialize CoprHD for VxRack. It takes the following actions sequentially
#
#  1. Mark completion of CoprHD initial configuration wizard
#  2. Cleanup stale records so that this script is reentrant
#  3. Upload Ansible playbook file
#  4. Create workflow
#  5. Create catalog category and services
#
# This script is re-entrant. It removes all VxRack related workflow, ansible package, catalog
# services before creating new.
#

import requests
import logging
logging.captureWarnings(True)
import sys
# validate arguments
if len(sys.argv) < 3:
    print "Usage: coprhd-init.py <CoprHD Virtual IP> <Path to Ansible ScaleIO Playbook Tar>"
    exit(1)

VIP=sys.argv[1]
ANSIBLE_TAR_FILE=sys.argv[2]
PASSWORD = "ChangeMe"

URI = "https://%s:4443" % VIP
HEADER_AUTH_TOKEN = "X-SDS-AUTH-TOKEN"
HEADER_CONTENT_TYPE = "Content-Type"
HEADER_ACCEPT = "ACCEPT"

WORKFLOW_NAME_ADD_NODE = "Add New Node"
WORKFLOW_NAME_REMOVE_NODE = "Remove ScaleIO Node"
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

def skipInitialConfig():
    url = "https://%s/api/setup/skip" % VIP;
    headers = {HEADER_AUTH_TOKEN: loginToken};
    resp = requests.put(url, verify = False, headers = headers)
    resp.raise_for_status()

def updateProxyPassword():
    url = URI + "/config/properties";
    headers = {HEADER_AUTH_TOKEN: loginToken,
               HEADER_CONTENT_TYPE: "application/xml",
               HEADER_ACCEPT: "application/json"};
    data = """
    <property_update>
      <properties>
          <entry><key>system_proxyuser_encpassword</key><value>%s</value></entry>
      </properties>
    </property_update>
             """ % PASSWORD;
    print "Updating proxy password"
    resp = requests.put(url, verify = False, headers = headers, data = data);
    resp.raise_for_status();
    print resp.text
    print resp.url


def uploadAnsiblePlaybook(name, playbookFile):
    url = URI + "/primitives/resource/ANSIBLE?name=%s" % name;
    headers = {HEADER_AUTH_TOKEN: loginToken,
           HEADER_CONTENT_TYPE: "application/octet-stream",
           HEADER_ACCEPT: "application/json"};
    file = open(playbookFile, 'rb');
    data = file.read();
    file.close()
    resp = requests.post(url, verify = False, headers = headers, data = data);
    resp.raise_for_status();
    json = resp.json();
    return json["id"];

def cleanupAnsiblePrimitive(playbookName):
    url = URI + "/primitives?type=ANSIBLE";
    headers = {HEADER_AUTH_TOKEN: loginToken, HEADER_ACCEPT: "application/json"};
    resp = requests.get(url, verify = False, headers = headers);
    resp.raise_for_status()
    json = resp.json()
    for primitive in json["primitive"]:
        url = URI + "/primitives/%s" % primitive;
        resp = requests.get(url, verify = False, headers = headers);
        resp.raise_for_status()
        primitiveJson = resp.json()
        if playbookName == primitiveJson["name"]:
            packageIdId = primitiveJson["resource"]["id"]
            # TODO delete the package first?
        url = URI + "/primitives/%s/deactivate" % primitive;
        resp = requests.post(url, verify = False, headers = headers);
        resp.raise_for_status()

def createAddNodePrimitive(ansiblePackageId):
    url = URI + "/primitives";
    headers = {HEADER_AUTH_TOKEN: loginToken,
               HEADER_CONTENT_TYPE: "application/xml",
               HEADER_ACCEPT: "application/json"};
    data = """ <primitive_create_param>
                 <attributes>
                     <entry>
                        <key>playbook</key>
                        <value>ansible-scaleio/site-add-sds.yml</value>
                     </entry>
                 </attributes>
                 <description>Ansible Playbook for Add ScaleIO Node</description>
                 <friendly_name>Add ScaleIO Node</friendly_name>
                 <name>Add ScaleIO Node</name>
                 <resource>%s</resource>
                 <type>ANSIBLE</type>
              </primitive_create_param> """ % ansiblePackageId;
    resp = requests.post(url, verify = False, headers = headers, data = data);
    resp.raise_for_status();
    json = resp.json();
    return json["id"];

def createRemoveNodePrimitive(ansiblePackageId):
    url = URI + "/primitives";
    headers = {HEADER_AUTH_TOKEN: loginToken,
               HEADER_CONTENT_TYPE: "application/xml",
               HEADER_ACCEPT: "application/json"};
    data = """ <primitive_create_param>
                 <attributes>
                     <entry>
                        <key>playbook</key>
                        <value>ansible-scaleio/remove_node_scaleio.yml</value>
                     </entry>
                 </attributes>
                 <description>Ansible Playbook for Remove ScaleIO Node</description>
                 <friendly_name>Remove ScaleIO Node</friendly_name>
                 <name>Remove ScaleIO Node</name>
                 <resource>%s</resource>
                 <type>ANSIBLE</type>
              </primitive_create_param> """ % ansiblePackageId;
    resp = requests.post(url, verify = False, headers = headers, data = data);
    resp.raise_for_status();
    json = resp.json();
    return json["id"];

def createWorkflowAddNode(ansiblePrimitiveId):
    url = URI + "/workflows";
    headers = {HEADER_AUTH_TOKEN: loginToken,
               HEADER_CONTENT_TYPE: "application/json",
               HEADER_ACCEPT: "application/json"};
    data = """
    { "document":
    {
    "name":"%s",
    "description":"Add a new ScaleIO node",
    "steps":[
      {
         "id":"Start",
         "next":{
            "default":"AddNewScaleIONode"
          }
      },
      {
         "id":"AddNewScaleIONode",
         "operation":"%s",
         "description":"Add a new ScaleIO node",
         "type":"Local Ansible",
         "inputGroups": {
         "input_params": {
            "input" : [
                        {
                           "name" : "scaleio_common_file_install_file_location",
                           "friendly_name" : "RPM Location",
                           "type" : "InputFromUser",
                           "default_value": "/data/scaleio"
                        },
                        {
                            "name" : "scaleio_interface",
                            "friendly_name" : "ScaleIO Interface",
                            "type" : "InputFromUser",
                            "default_value": "eth0"
                        },
                        {
                            "name" : "scaleio_sds_disks",
                            "friendly_name" : "ScaleIO SDS Disks",
                            "type" : "InputFromUser",
                            "default_value": ""
                        },
                        {
                            "name" : "scaleio_protection_domain",
                            "friendly_name" : "ScaleIO Protection Domain",
                            "type" : "InputFromUser",
                            "default_value": "default"
                        },
                        {
                            "name" : "scaleio_storage_pool",
                            "friendly_name" : "ScaleIO Storage Pool",
                            "type" : "InputFromUser",
                            "default_value": "default"
                        },
                        {
                            "name" : "mdm_hosts",
                            "friendly_name" : "ScaleIO MDM Hosts",
                            "type" : "InputFromUser",
                            "default_value": ""
                        },
                        {
                            "name" : "sds_hosts",
                            "friendly_name" : "ScaleIO SDS Hosts",
                            "type" : "InputFromUser",
                            "default_value": ""
                        }
              ]
          }
         },
         "attributes":{
            "wait_for_task":true,
            "timeout":"1000000",
            "host_key_checking":false
         },
         "success_criteria":null,
         "next":{
            "default":"End"
          }
      },
      {
         "id":"End"
      }
    ]
    }
    }
               """ % (WORKFLOW_NAME_ADD_NODE, ansiblePrimitiveId);
    resp = requests.post(url, verify = False, headers = headers, data = data);
    resp.raise_for_status();
    json = resp.json();
    return json["id"];

def createWorkflowRemoveNode(ansiblePrimitiveId):
    url = URI + "/workflows";
    headers = {HEADER_AUTH_TOKEN: loginToken,
               HEADER_CONTENT_TYPE: "application/json",
               HEADER_ACCEPT: "application/json"};
    data = """
    { "document":
    {
    "name":"%s",
    "description":"Remove ScaleIO node",
    "steps":[
      {
         "id":"Start",
         "next":{
            "default":"RemoveNewScaleIONode"
          }
      },
      {
         "id":"RemoveNewScaleIONode",
         "operation":"%s",
         "description":"Remove ScaleIO node",
         "type":"Local Ansible",
         "inputGroups": {
         "input_params": {
            "input" : [
                        {
                            "name" : "scaleio_interface",
                            "friendly_name" : "ScaleIO Interface",
                            "type" : "InputFromUser",
                            "default_value": "eth0"
                        },
                        {
                            "name" : "scaleio_volume_name",
                            "friendly_name" : "ScaleIO Volume Name",
                            "type" : "InputFromUser",
                            "default_value": ""
                        },
                        {
                            "name" : "mdm_hosts",
                            "friendly_name" : "ScaleIO MDM Hosts",
                            "type" : "InputFromUser",
                            "default_value": ""
                        },
                        {
                            "name" : "sds_hosts",
                            "friendly_name" : "ScaleIO SDS Hosts",
                            "type" : "InputFromUser",
                            "default_value": "",
                            "required":"false"
                        },
                        {
                            "name" : "sdc_hosts",
                            "friendly_name" : "ScaleIO SDC Hosts",
                            "type" : "InputFromUser",
                            "default_value": "",
                            "required":"false"
                        }
              ]
          }
         },
         "attributes":{
            "wait_for_task":true,
            "timeout":"1000000",
            "host_key_checking":false
         },
         "success_criteria":null,
         "next":{
            "default":"End"
          }
      },
      {
         "id":"End"
      }
    ]
    }
    }
               """ % (WORKFLOW_NAME_REMOVE_NODE, ansiblePrimitiveId);
    resp = requests.post(url, verify = False, headers = headers, data = data);
    resp.raise_for_status();
    json = resp.json();
    return json["id"];

def validateAndPublishWorkflow(workflowId):
    url = URI + "/workflows/%s/validate" % workflowId;
    headers = {HEADER_AUTH_TOKEN: loginToken}
    resp = requests.post(url, verify = False, headers = headers);
    resp.raise_for_status();

    url = URI + "/workflows/%s/publish" % workflowId;
    resp = requests.post(url, verify = False, headers = headers);
    resp.raise_for_status();

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

def cleanupWorkflow(workflowName):
    url = URI + "/workflows";
    headers = {HEADER_AUTH_TOKEN: loginToken, "ACCEPT": "application/json"};
    resp = requests.get(url, verify = False, headers = headers);
    resp.raise_for_status()
    json = resp.json()
    for workflow in json["workflows"]:
        if workflow["name"] == workflowName:
            url = URI + "/workflows/%s/unpublish" % workflow["id"];
            resp = requests.post(url, verify = False, headers = headers);
            resp.raise_for_status()
            url = URI + "/workflows/%s/deactivate" % workflow["id"];
            resp = requests.post(url, verify = False, headers = headers);
            resp.raise_for_status()

def cleanupVxRackCategory(rootCategoryId, categoryName):
    url = URI + "/catalog/categories/%s/categories" % rootCategoryId;
    headers = {HEADER_AUTH_TOKEN: loginToken, HEADER_ACCEPT: "application/json"};
    resp = requests.get(url, verify = False, headers = headers);
    resp.raise_for_status()
    json = resp.json()
    for category in json["catalog_category"]:
        if category["name"] == categoryName:
            url = URI + "/catalog/categories/%s/deactivate" % category["id"];
            resp = requests.post(url, verify = False, headers = headers);
            resp.raise_for_status()

def createVxRackCategory(rootCategoryId, rootTenantId):
    url = URI + "/catalog/categories";
    headers = {HEADER_AUTH_TOKEN: loginToken,
               HEADER_CONTENT_TYPE: "application/xml",
               HEADER_ACCEPT: "application/json"};
    data = """
<catalog_category_create>
    <catalog_category>%s</catalog_category>
    <description>%s</description>
    <image>icon_application.png</image>
    <name>%s</name>
    <title>%s</title>
    <tenantId>%s</tenantId>
</catalog_category_create>
               """ % (rootCategoryId, CATALOG_CATEGORY_NAME, CATALOG_CATEGORY_NAME, CATALOG_CATEGORY_NAME, rootTenantId);
    resp = requests.post(url, verify = False, headers = headers, data = data);
    resp.raise_for_status();
    json = resp.json();
    return json["id"];

def createCatalogServiceAddNode(categoryId):
    url = URI + "/catalog/services";
    headers = {HEADER_AUTH_TOKEN: loginToken,
               HEADER_CONTENT_TYPE: "application/xml",
               HEADER_ACCEPT: "application/json"};
    data = """
<catalog_service_create>
   <approval_required>false</approval_required>
   <base_service>%s</base_service>
   <catalog_category>%s</catalog_category>
   <description>Add a new ScaleIO node</description>
   <execution_window_required>false</execution_window_required>
   <image>icon_application.png</image>
   <max_size>0</max_size>
   <name>VxRackAddnewScaleIOnode</name>
   <title>VxRack - Add new ScaleIO node</title>
</catalog_service_create>
               """ % (WORKFLOW_NAME_ADD_NODE, categoryId);
    resp = requests.post(url, verify = False, headers = headers, data = data);
    resp.raise_for_status();
    json = resp.json();
    return json["id"];

def createCatalogServiceRemoveNode(categoryId):
    url = URI + "/catalog/services";
    headers = {HEADER_AUTH_TOKEN: loginToken,
               HEADER_CONTENT_TYPE: "application/xml",
               HEADER_ACCEPT: "application/json"};
    data = """
<catalog_service_create>
   <approval_required>false</approval_required>
   <base_service>%s</base_service>
   <catalog_category>%s</catalog_category>
   <description>Remove a ScaleIO node</description>
   <execution_window_required>false</execution_window_required>
   <image>icon_application.png</image>
   <max_size>0</max_size>
   <name>VxRackRemoveScaleIOnode</name>
   <title>VxRack - Remove ScaleIO node</title>
</catalog_service_create>
               """ % (WORKFLOW_NAME_REMOVE_NODE, categoryId);
    resp = requests.post(url, verify = False, headers = headers, data = data);
    resp.raise_for_status();
    json = resp.json();
    return json["id"];

loginToken = login();
state = checkClusterState();
if state != "STABLE":
    print "CoprHD cluster state is not stable %s. Please try again later" % state;
    exit(1);

print "CoprHD %s Cluster state is stable." % VIP
print "Start CoprHD initialization ..."
print

updateProxyPassword();
skipInitialConfig();
rootTenantId = getRootTenantId();
rootCategoryId = getRootCategoryId(rootTenantId);
print "Root tenant ID: %s" % rootTenantId
print "Root catalog category ID: %s" % rootCategoryId
print

print "Cleanup stale record ...",
cleanupVxRackCategory(rootCategoryId, CATALOG_CATEGORY_NAME);
cleanupWorkflow(WORKFLOW_NAME_ADD_NODE);
cleanupWorkflow(WORKFLOW_NAME_REMOVE_NODE);
cleanupAnsiblePrimitive("ansible-scaleio-master");
print "Done"

print "Upload Ansible playbook from %s ..." % ANSIBLE_TAR_FILE ,
ansiblePackageId = uploadAnsiblePlaybook("AnsibleScaleIO2", ANSIBLE_TAR_FILE);
addNodePrimitiveId = createAddNodePrimitive(ansiblePackageId);
removeNodePrimitiveId = createRemoveNodePrimitive(ansiblePackageId);
print "Done"

print "Create workflow ...",
addNodeWorkflowId = createWorkflowAddNode(addNodePrimitiveId);
validateAndPublishWorkflow(addNodeWorkflowId);
removeNodeWorkflowId = createWorkflowRemoveNode(removeNodePrimitiveId);
validateAndPublishWorkflow(removeNodeWorkflowId);
print "Done"

print "Create Catalog Service ...",
categoryId = createVxRackCategory(rootCategoryId, rootTenantId);
createCatalogServiceAddNode(categoryId);
createCatalogServiceRemoveNode(categoryId);
print "Done"
print

print "CoprHD initialization is done successfully."
