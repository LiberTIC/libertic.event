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
from Testing.makerequest import makerequest
from StringIO import StringIO

from libertic.event import setuphandlers

PRODUCT =  'libertic.event'
PROFILE =  '%s:default' % PRODUCT
PROFILEID = 'profile-%s' % PROFILE

def log(message, level='info'):
    logger = logging.getLogger('%s.upgrades' % PRODUCT)
    getattr(logger, level)(message)

def quickinstall_addons(context, install=None, uninstall=None, upgrades=None):
    qi = getToolByName(context, 'portal_quickinstaller')

    if install is not None:
        for addon in install:
            if qi.isProductInstallable(addon):
                qi.installProduct(addon)
                log('Installed %s' % addon)
            else:
                log('%s can t be installed' % addon, 'error')

    if uninstall is not None:
        for p in uninstall:
            if qi.isProductInstalled(p):
                qi.uninstallProducts([p])
                log('Uninstalled %s' % p)

    if upgrades is not None:
        if upgrades in ("all", True):
            # find which addons should be upgrades
            installedProducts = qi.listInstalledProducts(showHidden=True)
            upgrades = [p['id'] for p in installedProducts]
        for upgrade in upgrades:
            # do not try to upgrade myself -> recursion
            if upgrade == PRODUCT:
                continue
            try:
                qi.upgradeProduct(upgrade)
                log('Upgraded %s' % upgrade)
            except KeyError:
                log('can t upgrade %s' % upgrade, 'error')

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

def upgrade_plone(portal_setup):
    """
    """
    out = StringIO()
    portal = makerequest(
        getToolByName(
            portal_setup, 'portal_url'
        ).getPortalObject(),
        stdout=out, environ={'REQUEST_METHOD':'POST'})
    # pm = getToolByName(portal, 'portal_migration')
    # use direct acquisition for REQUEST to be always there
    pm = portal.portal_migration
    report = pm.upgrade(dry_run=False)
    return report

def upgrade_1001(context):
    """
    """
    site = getToolByName(context, 'portal_url').getPortalObject()
    portal_setup = site.portal_setup
    portal_setup.runImportStepFromProfile('profile-libertic.event:default', 'typeinfo', run_dependencies=False)
    portal_setup.runImportStepFromProfile('profile-libertic.event:default', 'collective.cron.setupCrons', run_dependencies=False)
    portal_setup.runImportStepFromProfile('profile-libertic.event:default', 'plone.app.registry', run_dependencies=False)
    setuphandlers.setup_catalog(site)
    log('v1001 applied')


def upgrade_1002(context):
    """
    """
    site = getToolByName(context, 'portal_url').getPortalObject()
    setuphandlers.setup_catalog(site)
    setuphandlers.full_reindex(site)
    portal_setup = site.portal_setup
    portal_setup.runImportStepFromProfile(PROFILEID, 'typeinfo', run_dependencies=False)
    setuphandlers.configure_extra(site)
    quickinstall_addons(site, ['collective.datatablesviews'], upgrades=True)
    portal_setup.runImportStepFromProfile(PROFILEID, 'workflow', run_dependencies=False)
    portal_setup.runImportStepFromProfile(PROFILEID, 'plone.app.theming', run_dependencies=False)
    portal_setup.runImportStepFromProfile(PROFILEID, 'plone.app.registry', run_dependencies=False)
    portal_setup.runImportStepFromProfile(PROFILEID, 'portlets', run_dependencies=False)
    portal_setup.runImportStepFromProfile(PROFILEID, 'atcttool', run_dependencies=False)
    portal_setup.runImportStepFromProfile('profile-collective.datatablesviews:default', 'typeinfo', run_dependencies=False)
    import_js(context)
    import_css(context)
    recook_resources(context)
    log('v1002 applied')

def upgrade_1003(context):
    site = getToolByName(context, 'portal_url').getPortalObject()
    upgrade_plone(context)
    quickinstall_addons(context, upgrades=True)
    log('v1003 applied')

def upgrade_1004(context):
    """ """
    site = getToolByName(context, 'portal_url').getPortalObject()
    portal_setup = site.portal_setup
    portal_setup.runImportStepFromProfile(PROFILEID, 'portlets', run_dependencies=False)
    log('v1004 applied')

def upgrade_1005(context):
    """ """
    site = getToolByName(context, 'portal_url').getPortalObject()
    portal_setup = getToolByName(site, 'portal_setup')
    setuphandlers.install_groups(context)
    portal_setup.runImportStepFromProfile(PROFILEID, 'plone.app.registry', run_dependencies=False)
    log('v1005 applied')

def upgrade_1006(context):
    site = getToolByName(context, 'portal_url').getPortalObject()
    quickinstall_addons(
        context,
        install= ['plone.app.relationfield',
                  'collective.js.masonry',
                  'collective.js.imagesloaded'],
        upgrades=True)
    log('v1006 applied')

def upgrade_1007(context):
    import_js(context)
    import_css(context)
    recook_resources(context)
    log('v1006 applied')

def upgrade_1008(context):
    """ """
    site = getToolByName(context, 'portal_url').getPortalObject()
    portal_setup = site.portal_setup
    portal_setup.runImportStepFromProfile(PROFILEID, 'portlets', run_dependencies=False)
    log('v1008 applied')

def upgrade_1010(context):
    """ """
    site = getToolByName(context, 'portal_url').getPortalObject()
    portal_setup = site.portal_setup
    portal_setup.runImportStepFromProfile(PROFILEID, 'typeinfo', run_dependencies=False)
