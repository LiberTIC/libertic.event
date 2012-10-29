# -*- coding: utf-8 -*-

import os, sys
import logging

try:
    from Products.CMFPlone.migrations import migration_util
except:
    #plone4
    from plone.app.upgrade import utils as migration_util

from Products.CMFCore.utils import getToolByName
from Products.ATContentTypes.interface.image import IATImage
from Products.ATContentTypes.content.image import ATImage
import transaction


from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.utils import _createObjectByType

from libertic.event import setuphandlers

PROFILE =  'libertic.event:default'
PROFILEID = 'profile-%s' % PROFILE

def log(message):
    logger = logging.getLogger('libertic.event.upgrades')
    logger.warn(message)

def recook_resources(context):
    """
    """
    site = getToolByName(context, 'portal_url').getPortalObject()
    jsregistry = getToolByName(site, 'portal_javascripts')
    cssregistry = getToolByName(site, 'portal_css')
    jsregistry.cookResources()
    cssregistry.cookResources()
    log('Recooked css/js')

def import_js(context):
    """
    """
    site = getToolByName(context, 'portal_url').getPortalObject()
    portal_setup = getToolByName(context, 'portal_setup')
    portal_setup.runImportStepFromProfile(PROFILEID, 'jsregistry', run_dependencies=False)
    log('Imported js')

def import_css(context):
    """
    """
    site = getToolByName(context, 'portal_url').getPortalObject()
    portal_setup = getToolByName(context, 'portal_setup')
    portal_setup.runImportStepFromProfile(PROFILEID, 'cssregistry', run_dependencies=False)
    log('Imported css')

def upgrade_profile(context, profile_id, steps=None):
    """
    >>> upgrade_profile(context, 'foo:default')
    """
    portal_setup = getToolByName(context.aq_parent, 'portal_setup')
    gsteps = portal_setup.listUpgrades(profile_id)
    class fakeresponse(object):
        def redirect(self, *a, **kw): pass
    class fakerequest(object):
        RESPONSE = fakeresponse()
        def __init__(self):
            self.form = {}
            self.get = self.form.get
    fr = fakerequest()
    if steps is None:
        steps = []
        for col in gsteps:
            if not isinstance(col, list):
                col = [col]
            for ustep in col:
                steps.append(ustep['id'])
        fr.form.update({
            'profile_id': profile_id,
            'upgrades': steps,
        })
    portal_setup.manage_doUpgrades(fr)

def upgrade_1001(context):
    """
    """
    site = getToolByName(context, 'portal_url').getPortalObject()
    portal_setup = site.portal_setup
    # install Products.PloneSurvey and dependencies
    #migration_util.loadMigrationProfile(site,
    #                                    'profile-Products.PloneSurvey:default')
    #portal_setup.runImportStepFromProfile('profile-libertic.event:default', 'jsregistry', run_dependencies=False)
    #portal_setup.runImportStepFromProfile('profile-libertic.event:default', 'cssregistry', run_dependencies=False)
    #portal_setup.runImportStepFromProfile('profile-libertic.event:default', 'portlets', run_dependencies=False)
    #portal_setup.runImportStepFromProfile('profile-libertic.event:default', 'propertiestool', run_dependencies=False)
    portal_setup.runImportStepFromProfile('profile-libertic.event:default', 'typeinfo', run_dependencies=False)
    portal_setup.runImportStepFromProfile('profile-libertic.event:default', 'collective.cron.setupCrons', run_dependencies=False)
    portal_setup.runImportStepFromProfile('profile-libertic.event:default', 'plone.app.registry', run_dependencies=False) 
    setuphandlers.setup_catalog(site)
    log('v1001 applied')


