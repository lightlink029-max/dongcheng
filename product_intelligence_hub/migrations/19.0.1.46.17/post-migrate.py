def migrate(cr, version):
    cr.execute("""
        UPDATE res_partner AS partner
           SET phone = COALESCE(NULLIF(offer.contact_phone, ''), NULLIF(offer.contact_landline, ''), partner.phone),
               email = COALESCE(NULLIF(offer.contact_email, ''), partner.email)
          FROM product_intelligence_sourcing_offer AS offer
         WHERE offer.supplier_partner_id = partner.id
           AND (NULLIF(offer.contact_phone, '') IS NOT NULL
                OR NULLIF(offer.contact_landline, '') IS NOT NULL
                OR NULLIF(offer.contact_email, '') IS NOT NULL)
    """)
