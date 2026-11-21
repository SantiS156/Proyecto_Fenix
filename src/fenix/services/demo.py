"""Laboratorio acotado de recursos. Integrante 2 prepara, integrante 6 verifica."""
from botocore.exceptions import ClientError
from fenix.config.settings import client
from fenix.utils.errors import PermanentError
from fenix.utils.state import load, save
from fenix.utils.validation import identifier
import time
from fenix.utils.errors import ValidationError

def _tags_to_dict(tags: list[dict[str, str]] | None) -> dict[str, str]:
    return {t["Key"]: t["Value"] for t in (tags or [])}


def _aws_tags(values: dict[str, str]) -> list[dict[str, str]]:
    return [{"Key": k, "Value": v} for k, v in values.items()]


def setup_demo(group: str) -> dict:
    """Prepara una instancia mock y un bucket a partir de identificadores estables.

    Args:
        group: ID validado del grupo; determina prefijos de los recursos.
    Returns:
        Inventario con aliases node-01 y bucket-01 y sus IDs reales del emulador.
    Raises:
        ClientError: Si el emulador no soporta una operación o falla su ejecución.
    Side Effects:
        Crea recursos de laboratorio etiquetados y data/inventory.json.
    Notes:
        Reutilizar por tags antes de crear y guardar IDs después de cada creación.
        Obtener una ImageId con describe_images; no copiar una AMI de AWS real.
    """
    group_id = identifier(group)
    ec2 = client("ec2")
    s3 = client("s3")

    state = load("data/inventory.json")

    vpcs = ec2.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])["Vpcs"]
    if not vpcs:
        raise PermanentError("No se encontró VPC predeterminada")
    vpc_id = vpcs[0]["VpcId"]

    images = ec2.describe_images()["Images"]
    if not images:
        raise PermanentError("No hay imágenes disponibles en el emulador")
    image_id = sorted(images, key=lambda row: row["ImageId"])[0]["ImageId"]

    sg_name = f"fenix-{group_id}-sg"
    sg_tags = {"ManagedBy": "ppa2", "GroupId": group_id}
    sg_id = None

    existing_sgs = ec2.describe_security_groups(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "tag:ManagedBy", "Values": ["ppa2"]},
            {"Name": "tag:GroupId", "Values": [group_id]},
        ]
    )["SecurityGroups"]
    for sg in existing_sgs:
        sg_dict = _tags_to_dict(sg.get("Tags"))
        if (
            sg.get("GroupName") == sg_name
            and sg_dict.get("ManagedBy") == "ppa2"
            and sg_dict.get("GroupId") == group_id
        ):
            sg_id = sg["GroupId"]
            break

    if not sg_id:
        try:
            sg_id = ec2.create_security_group(
                GroupName=sg_name,
                Description=f"Laboratorio Fénix {group_id}",
                VpcId=vpc_id,
                TagSpecifications=[
                    {"ResourceType": "security-group", "Tags": _aws_tags(sg_tags)}
                ],
            )["GroupId"]
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "InvalidGroup.Duplicate":
                raise
            found = ec2.describe_security_groups(
                Filters=[
                    {"Name": "vpc-id", "Values": [vpc_id]},
                    {"Name": "group-name", "Values": [sg_name]},
                ]
            )["SecurityGroups"]
            sg_id = found[0]["GroupId"]
            ec2.create_tags(Resources=[sg_id], Tags=_aws_tags(sg_tags))

    node_name = f"fenix-{group_id}-node-01"
    inst_tags = {
        "Project": "fenix",
        "GroupId": group_id,
        "ManagedBy": "ppa2",
        "Name": node_name,
    }
    instance_id = None

    reservations = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Project", "Values": ["fenix"]},
            {"Name": "tag:GroupId", "Values": [group_id]},
            {"Name": "tag:Name", "Values": [node_name]},
            {
                "Name": "instance-state-name",
                "Values": ["pending", "running", "stopping", "stopped"],
            },
        ]
    )["Reservations"]
    for res in reservations:
        for inst in res.get("Instances", []):
            inst_dict = _tags_to_dict(inst.get("Tags"))
            if (
                inst_dict.get("Project") == "fenix"
                and inst_dict.get("GroupId") == group_id
                and inst_dict.get("Name") == node_name
            ):
                instance_id = inst["InstanceId"]
                break
        if instance_id:
            break

    if not instance_id:
        client_token = f"fenix-{group_id}-node-01"[:64]
        run_resp = ec2.run_instances(
            ImageId=image_id,
            InstanceType="t3.micro",
            MinCount=1,
            MaxCount=1,
            SecurityGroupIds=[sg_id],
            ClientToken=client_token,
            TagSpecifications=[
                {"ResourceType": "instance", "Tags": _aws_tags(inst_tags)}
            ],
        )
        instance_id = run_resp["Instances"][0]["InstanceId"]

    bucket_name = f"fenix-{group_id}-demo"
    bucket_tags = {
        "ManagedBy": "ppa2",
        "Project": "fenix",
        "GroupId": group_id,
        "Owner": group_id,
    }

    existing_buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    if bucket_name not in existing_buckets:
        try:
            s3.create_bucket(Bucket=bucket_name)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in ("BucketAlreadyExists", "BucketAlreadyOwnedByYou"):
                raise

    s3.put_bucket_tagging(
        Bucket=bucket_name,
        Tagging={"TagSet": _aws_tags(bucket_tags)},
    )

    verified_tags = _tags_to_dict(
        s3.get_bucket_tagging(Bucket=bucket_name).get("TagSet", [])
    )
    if (
        verified_tags.get("ManagedBy") != "ppa2"
        or verified_tags.get("Project") != "fenix"
        or verified_tags.get("GroupId") != group_id
        or verified_tags.get("Owner") != group_id
    ):
        raise PermanentError("No se pudo verificar la propiedad del bucket de laboratorio")

    inventory = {
    "group": group_id,
    "resources": {
        "node-01": {
            "type": "ec2",
            "id": instance_id,
            "name": node_name,
            "vpc_id": vpc_id,
            "image_id": image_id,
            "security_group_id": sg_id,
        },
        "bucket-01": {
            "type": "s3",
            "name": bucket_name,
            "region": "us-east-1",
        },
    },
}

    if isinstance(state, dict):
        state.update(inventory)
        save("data/inventory.json", state)
    else:
        save("data/inventory.json", inventory)

    return inventory



def inject_fault(alias: str) -> None:
    """Introduce y verifica un fallo controlado en un recurso autorizado."""

    inventory = load("data/inventory.json")
    resources = inventory.get("resources", {})

    resource = resources.get(alias)

    if not isinstance(resource, dict):
        raise ValidationError("El alias no pertenece al inventario")

    if alias == "node-01":
        if resource.get("type") != "ec2":
            raise ValidationError("El recurso no es una instancia EC2")

        instance_id = resource.get("id")
        if not instance_id:
            raise ValidationError("La instancia no tiene un ID válido")

        ec2 = client("ec2")

        current = ec2.describe_instances(
            InstanceIds=[instance_id]
        )["Reservations"][0]["Instances"][0]["State"]["Name"]

        if current != "stopped":
            ec2.stop_instances(InstanceIds=[instance_id])

        # Comprobar el estado con un límite de espera.
        for _ in range(20):
            response = ec2.describe_instances(
                InstanceIds=[instance_id]
            )
            status = response["Reservations"][0]["Instances"][0]["State"]["Name"]

            if status == "stopped":
                return

            time.sleep(1)

        raise PermanentError("No se pudo verificar el estado stopped")

    elif alias == "bucket-01":
        if resource.get("type") != "s3":
            raise ValidationError("El recurso no es un bucket S3")

        bucket_name = resource.get("name")
        if not bucket_name:
            raise ValidationError("El bucket no tiene un nombre válido")

        s3 = client("s3")

        tags = s3.get_bucket_tagging(
            Bucket=bucket_name
        ).get("TagSet", [])

        # Conservar todas las etiquetas excepto Owner.
        remaining_tags = [
            tag for tag in tags
            if tag["Key"] != "Owner"
        ]

        if len(remaining_tags) != len(tags):
            s3.put_bucket_tagging(
                Bucket=bucket_name,
                Tagging={"TagSet": remaining_tags},
            )

        # Verificar que Owner ya no exista.
        verified_tags = s3.get_bucket_tagging(
            Bucket=bucket_name
        ).get("TagSet", [])

        if any(tag["Key"] == "Owner" for tag in verified_tags):
            raise PermanentError("No se pudo eliminar la etiqueta Owner")

        return

    raise ValidationError("Alias no permitido")

