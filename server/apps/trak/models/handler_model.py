import logging
from typing import Union

from django.core.exceptions import ValidationError
from django.db import models

from .address_model import Address
from .base_model import TrakBaseManager, TrakBaseModel
from .contact_model import Contact, EpaPhone
from .signature_model import ESignature, PaperSignature

logger = logging.getLogger(__name__)


class HandlerManager(TrakBaseManager):
    """
    Inter-model related functionality for Handler Model
    """

    def __init__(self):
        self.handler_data = None
        super().__init__()

    def save(self, **handler_data):
        """
        Create a handler and its related fields

        Keyword Args:
            contact (dict): Contact data in (ordered)dict format
            site_address (dict): Site address data dict
            mail_address (dict): mailing address data dict
            emergency_phone (dict): optional Phone dict
        """
        try:
            epa_id = handler_data.get("epa_id")
            if self.model.objects.filter(epa_id=epa_id).exists():
                return Handler.objects.get(epa_id=epa_id)
            self.handler_data = handler_data
            new_contact = Contact.objects.save(**self.handler_data.pop("contact"))
            emergency_phone = self.get_emergency_phone()
            site_address = self.get_address("site_address")
            mail_address = self.get_address("mail_address")
            return super().save(
                site_address=site_address,
                mail_address=mail_address,
                emergency_phone=emergency_phone,
                contact=new_contact,
                **self.handler_data,
            )
        except KeyError as exc:
            logger.warning(f"error while creating handler {exc}")

    def get_emergency_phone(self) -> Union[EpaPhone, None]:
        """Check if emergency phone is present and create an EpaPhone row"""
        try:
            emergency_phone_data = self.handler_data.pop("emergency_phone")
            if emergency_phone_data is not None:
                return EpaPhone.objects.create(**emergency_phone_data)
        except KeyError as exc:
            logger.debug(exc)
            return None

    def get_address(self, key) -> Address:
        """Remove Address data and create if necessary"""
        try:
            address = self.handler_data.pop(key)
            if isinstance(address, Address):
                return address
            return Address.objects.create(**address)
        except KeyError as exc:
            logger.warning(exc)
            raise ValidationError(exc)


class Handler(TrakBaseModel):
    """
    RCRAInfo Handler model definition for entities on the uniform hazardous waste manifests
    """

    objects = HandlerManager()

    site_type = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        choices=[
            ("Tsdf", "Tsdf"),
            ("Generator", "Generator"),
            ("Transporter", "Transporter"),
            ("Broker", "Broker"),
        ],
    )
    epa_id = models.CharField(
        verbose_name="EPA Id number",
        max_length=25,
        unique=True,
    )
    name = models.CharField(
        max_length=200,
    )
    site_address = models.ForeignKey(
        "Address",
        on_delete=models.CASCADE,
        related_name="site_address",
    )
    mail_address = models.ForeignKey(
        "Address",
        on_delete=models.CASCADE,
        related_name="mail_address",
    )
    modified = models.BooleanField(
        null=True,
        blank=True,
    )
    registered = models.BooleanField(
        null=True,
        blank=True,
    )
    contact = models.ForeignKey(
        "Contact",
        on_delete=models.CASCADE,
        verbose_name="Contact Information",
    )
    emergency_phone = models.ForeignKey(
        "EpaPhone",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    gis_primary = models.BooleanField(
        verbose_name="GIS primary",
        null=True,
        blank=True,
        default=False,
    )
    can_esign = models.BooleanField(
        verbose_name="Can electronically sign",
        null=True,
        blank=True,
    )
    limited_esign = models.BooleanField(
        verbose_name="Limited electronic signing ability",
        null=True,
        blank=True,
    )
    registered_emanifest_user = models.BooleanField(
        verbose_name="Has Registered e-manifest user",
        null=True,
        blank=True,
        default=False,
    )

    def __str__(self):
        return f"{self.epa_id}"


class ManifestHandlerManager(TrakBaseManager):
    """
    Inter-model related functionality for ManifestHandler Model
    """

    def save(self, **handler_data) -> models.QuerySet:
        e_signatures = []
        paper_signature = None
        if "e_signatures" in handler_data:
            e_signatures = handler_data.pop("e_signatures")
        logger.debug(f"e_signature data {e_signatures}")
        if "paper_signature" in handler_data:
            paper_signature = PaperSignature.objects.create(**handler_data.pop("paper_signature"))
        try:
            if Handler.objects.filter(epa_id=handler_data["handler"]["epa_id"]).exists():
                handler = Handler.objects.get(epa_id=handler_data["handler"]["epa_id"])
                handler_data.pop("handler")
                logger.debug(f"using existing Handler {handler}")
            else:
                handler = Handler.objects.save(**handler_data.pop("handler"))
                logger.debug(f"Handler created {handler}")
            manifest_handler = self.model.objects.create(
                handler=handler,
                paper_signature=paper_signature,
                **handler_data,
            )
            logger.debug(f"ManifestHandler created {manifest_handler}")
            for e_signature_data in e_signatures:
                e_sig = ESignature.objects.save(
                    manifest_handler=manifest_handler, **e_signature_data
                )
                logger.debug(f"ESignature created {e_sig}")
            return manifest_handler
        except KeyError as exc:
            logger.warning(f"KeyError while creating Manifest handler {exc}")
        except ValidationError as exc:
            logger.warning(f"ValidationError while creating Manifest handler {exc}")
            raise exc


class ManifestHandler(TrakBaseModel):
    """
    ManifestHandler which contains a reference to hazardous waste
    handler and data specific to that handler on the given manifest.
    """

    objects = ManifestHandlerManager()

    handler = models.ForeignKey(
        "Handler",
        on_delete=models.CASCADE,
        help_text="Hazardous waste handler associated with the manifest",
    )
    paper_signature = models.OneToOneField(
        "PaperSignature",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The signature associated with hazardous waste custody exchange",
    )

    @property
    def signed(self) -> bool:
        """Returns True if one of the signature types is present"""
        e_signature_exists = ESignature.objects.filter(manifest_handler=self).exists()
        paper_signature_exists = self.paper_signature is not None
        return paper_signature_exists or e_signature_exists

    def __str__(self):
        return f"ManifestHandler: {self.handler.epa_id}"
