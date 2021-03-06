﻿# QUANTCONNECT.COM - Democratizing Finance, Empowering Individuals.
# Lean Algorithmic Trading Engine v2.0. Copyright 2014 QuantConnect Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from clr import AddReference
from clr import GetClrType as typeof
AddReference("System")
AddReference("QuantConnect.Common")
AddReference("QuantConnect.Algorithm.Framework")

from QuantConnect import *
from QuantConnect.Securities import *
from QuantConnect.Data.Auxiliary import ZipEntryName
from QuantConnect.Data.UniverseSelection import OptionChainUniverse
from Selection.UniverseSelectionModel import UniverseSelectionModel
from datetime import datetime

class OptionUniverseSelectionModel(UniverseSelectionModel):

    def __init__(self,
                 refreshInterval,
                 optionChainSymbolSelector,
                 universeSettings = None, 
                 securityInitializer = None):

        self.nextRefreshTimeUtc = datetime.min

        self.refreshInterval = refreshInterval
        self.optionChainSymbolSelector = optionChainSymbolSelector
        self.universeSettings = universeSettings
        self.securityInitializer = securityInitializer

    def GetNextRefreshTimeUtc(self):
        return self.nextRefreshTimeUtc

    def CreateUniverses(self, algorithm):
        self.nextRefreshTimeUtc = (algorithm.UtcTime + self.refreshInterval).date()

        algorithm.Log(f"OptionUniverseSelectionModel.CreateUniverse({algorithm.UtcTime}): Refreshing Universes")

        uniqueUnderlyingSymbols = set()
        for optionSymbol in self.optionChainSymbolSelector(algorithm.UtcTime):
            if optionSymbol.SecurityType != SecurityType.Option:
                raise ValueError("optionChainSymbolSelector must return option symbols.")

            # prevent creating duplicate option chains -- one per underlying
            if optionSymbol.Underlying not in uniqueUnderlyingSymbols:
                uniqueUnderlyingSymbols.add(optionSymbol.Underlying)
                yield self.CreateOptionChain(algorithm, optionSymbol)

    def CreateOptionChain(self, algorithm, symbol):
        if symbol.SecurityType != SecurityType.Option:
            raise ValueError("CreateOptionChain requires an option symbol.")

        algorithm.Log(f"OptionUniverseSelectionModel.CreateOptionChain({algorithm.UtcTime}, {symbol}): Creating Option Chain")

        # rewrite non-canonical symbols to be canonical
        market = symbol.ID.Market
        underlying = symbol.Underlying
        if not symbol.IsCanonical():
            alias = f"?{underlying.Value}"
            symbol = Symbol.Create(underlying.Value, SecurityType.Option, market, alias)

        # resolve defaults if not specified
        settings = self.universeSettings if self.universeSettings is not None else algorithm.UniverseSettings
        initializer = self.securityInitializer if self.securityInitializer is not None else algorithm.SecurityInitializer
        # create canonical security object, but don't duplicate if it already exists
        securities = [s for s in algorithm.Securities if s.Key == symbol]
        if len(securities) == 0:
            optionChain = self.CreateOptionChainSecurity(algorithm, symbol, settings, initializer)
        else:
            optionChain = securities[0]

            algorithm.Log(f"OptionUniverseSelectionModel.CreateOptionChain({algorithm.UtcTime}, {symbol}): Resolved existing Option Chain Security")

        # set the option chain contract filter function
        optionChain.SetFilter(self.Filter)

        # force option chain security to not be directly tradable AFTER it's configured to ensure it's not overwritten
        optionChain.IsTradable = False

        return OptionChainUniverse(optionChain, settings, initializer, algorithm.LiveMode)

    def CreateOptionChainSecurity(self, algorithm, symbol, settings, initializer):

        algorithm.Log(f"OptionUniverseSelectionModel.CreateOptionChainSecurity({algorithm.UtcTime}, {symbol}): Creating Option Chain Security")

        market = symbol.ID.Market
        underlying = symbol.Underlying

        marketHoursEntry = MarketHoursDatabase.FromDataFolder().GetEntry(market, underlying, SecurityType.Option)
        symbolProperties = SymbolPropertiesDatabase.FromDataFolder().GetSymbolProperties(market, underlying, SecurityType.Option, CashBook.AccountCurrency)

        return SecurityManager.CreateSecurity(typeof(ZipEntryName), algorithm.Portfolio,
                algorithm.SubscriptionManager, marketHoursEntry.ExchangeHours, marketHoursEntry.DataTimeZone, symbolProperties,
                initializer, symbol, settings.Resolution, settings.FillForward, settings.Leverage, settings.ExtendedMarketHours,
                False, False, algorithm.LiveMode, False, False)

    def Filter(self, filter):
        '''Defines the option chain universe filter'''
        # NOP
        return filter