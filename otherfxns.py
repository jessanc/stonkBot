#This module should be any function that doesn't require alpaca or keys to use
import json,requests,os,time,re,csv,math
import datetime as dt
from bs4 import BeautifulSoup as bs

apiKeys = {}
stockDir = ''

def init(keyFilePath, stockDataDir):
  global apiKeys, stockDir
  keyFile = open(keyFilePath,"r")
  apiKeys = json.loads(keyFile.read())
  keyFile.close()
  
  stockDir = stockDataDir

def isTradable(symb):
  isTradable = False
  while True:
    try:
      r = requests.request("GET","https://api.nasdaq.com/api/quote/{}/info?assetclass=stocks".format(symb), headers={"user-agent":"-"}).content
      break
    except Exception:
      print("No connection, or other error encountered, trying again...")
      time.sleep(3)
      continue
  try:
    isTradable = bool(json.loads(r)['data']['isNasdaqListed'])
  except Exception:
    print("Error in isTradable")

  return isTradable

#get list of stocks from stocksUnder1 and marketWatch lists
def getList():
  symbList = list()
  
  url = 'https://www.marketwatch.com/tools/stockresearch/screener/results.asp'
  #many of the options listed are optional and can be removed from the get request
  params = {
    "TradesShareEnable" : "True", 
    "TradesShareMin" : "0.8",
    "TradesShareMax" : "5",
    "PriceDirEnable" : "False",
    "PriceDir" : "Up",
    "LastYearEnable" : "False",
    "TradeVolEnable" : "true",
    "TradeVolMin" : "300000",
    "TradeVolMax" : "",
    "BlockEnable" : "False",
    "PERatioEnable" : "False",
    "MktCapEnable" : "False",
    "MovAvgEnable" : "False",
    "MktIdxEnable" : "False",
    "Exchange" : "NASDAQ",
    "IndustryEnable" : "False",
    "Symbol" : "True",
    "CompanyName" : "False",
    "Price" : "False",
    "Change" : "False",
    "ChangePct" : "False",
    "Volume" : "False",
    "LastTradeTime" : "False",
    "FiftyTwoWeekHigh" : "False",
    "FiftyTwoWeekLow" : "False",
    "PERatio" : "False",
    "MarketCap" : "False",
    "MoreInfo" : "False",
    "SortyBy" : "Symbol",
    "SortDirection" : "Ascending",
    "ResultsPerPage" : "OneHundred"
  }
  params['PagingIndex'] = 0 #this will change to show us where in the list we should be - increment by 100 (see ResultsPerPage key)
  
  while True:
    try:
      r = requests.get(url, params=params).text
      totalStocks = int(r.split("matches")[0].split("floatleft results")[1].split("of ")[1]) #get the total number of stocks in the list - important because they're spread over multiple pages
      break
    except Exception:
      print("No connection or other error encountered. Trying again...")
      time.sleep(3)
      continue
      
      
  print("Getting MarketWatch data...")
  for i in range(0,totalStocks,100): #loop through the pages (100 because ResultsPerPage is OneHundred)
    print(f"page {int(i/100)+1} of {math.ceil(totalStocks/100)}")
    params['PagingIndex'] = i
    while True:
      try:
        r = requests.get(url, params=params).text
        break
      except Exception:
        print("No connection or other error encountered. Trying again...")
        time.sleep(3)
        continue
    table = bs(r,'html.parser').find_all('table')[0]
    for e in table.find_all('tr')[1::]:
      symbList.append(e.find_all('td')[0].get_text())

  
  
  #now that we have the marketWatch list, let's get the stocksunder1 list - essentially the getPennies() fxn from other files
  url = 'https://stocksunder1.org/nasdaq-penny-stocks/'
  print("Getting stocksunder1 data...")
  while True:
    try:
      html = requests.post(url, params={"price":5,"volume":0,"updown":"up"}).content
      break
    except Exception:
      print("No connection, or other error encountered. Trying again...")
      time.sleep(3)
      continue

  table = bs(html,'html.parser').find_all('table')[6] #6th table in the webpage - this may change depending on the webpage
  symList = list()
  for e in table.find_all('tr')[1::]: #skip the first element that's the header
    #print(re.sub(r'\W+','',e.find_all('td')[0].get_text().replace(' predictions','')))
    symList += re.sub(r'\W+','',e.find_all('td')[0].get_text().replace(' predictions',''))
  
  print("Removing Duplicates...")
  symbList = list(set(symbList+symList)) #combine and remove duplicates
  
  print("Done getting stock lists")
  return symbList

#get the history of a stock from the nasdaq api (date format is yyyy-mm-dd)
#returns as 2d array order of Date, Close/Last, Volume, Open, High, Low sorted by dates newest to oldest
def getHistory(symb, startDate, endDate):
  #try checking the modified date of the file, if it throws an error, just set it to yesterday
  try:
    modDate = dt.datetime.strptime(time.strftime("%Y-%m-%d",time.localtime(os.stat(stockDir+symb+'.csv').st_mtime)),"%Y-%m-%d").date() #if ANYONE knows of a better way to get the mod date into a date format, for the love of god please let me know
  except Exception:
    modDate = dt.date.today()-dt.timedelta(1)
  #write to file after checking that the file doesn't already exist (we don't want to abuse the api) or that it was edited more than a day ago
  if(not os.path.isfile(stockDir+symb+".csv") or modDate<dt.date.today()):
    url = f'https://www.nasdaq.com/api/v1/historical/{symb}/stocks/{startDate}/{endDate}/'
    while True:
      try:
        r = requests.get(url, headers={"user-agent":"-"}).text #send request and store response - cannot have empty user-agent
        break
      except Exception:
        print("No connection, or other error encountered. Trying again...")
        time.sleep(3)
        continue
    out = open(stockDir+symb+'.csv','w') #write to file for later usage
    out.write(r)
    out.close()

  #read csv and convert to array
  #TODO: see if we can not have to save it to a file if possible due to high read/writes - can also eliminate csv library
  with open(stockDir+symb+".csv") as csv_file:
    csv_reader = csv.reader(csv_file, delimiter=',')
    out = [[ee.replace('$','').replace('N/A','0') for ee in e] for e in csv_reader][1::] #trim first line to get rid of headers, also replace $'s and N/A volumes to calculable values

  return out


#checks whether something is a good buy or not (if not, return why - no initial jump or second jump already missed).
#if it is a good buy, return initial jump date
#this is where the magic really happens

#TODO: check if currently held stock already peaked (i.e. we missed it while holding it) - if it did then lower expectations and try to sell at a profit still(this should only happen is there's a network error or during testing stuff)
def goodBuy(symb,days2look=25): #days2look=how farback to look for a jump
  validBuy = "NA" #set to the jump date if it's valid
  if isTradable(symb):
    #calc price % diff over past 20 days (current price/price of day n) - current must be >= 80% for any
    #calc volume % diff over average past some days (~60 days?) - must be sufficiently higher (~300% higher?)
    
    days2wait4fall = 3 #wait for stock price to fall for this many days
    startDate = days2wait4fall+1 #add 1 to account for the jump day itself
    firstJumpAmt = 1.3 #stock first must jump by this amount (1.3=130% over 1 day)
    sellUp = 1.25 #% to sell up at
    sellDn = 0.5 #% to sell dn at
    
    #make sure that the jump happened in the time frame rather than too long ago
    volAvgDays = 60 #arbitrary number to avg volumes over
    checkPriceDays = 30 #check if the price jumped substantially over the last __ trade days
    checkPriceAmt = 1.7 #check if the price jumped by this amount in the above days (% - i.e 1.5 = 150%)
    volGain = 3 #check if the volume increased by this amount during the jump (i.e. 3 = 300% or 3x, 0.5 = 50% or 0.5x)
    volLoss = .5 #check if the volume decreases by this amount during the price drop
    priceDrop = .4 #price should drop this far when the volume drops
    
    dateData = getHistory(symb, str(dt.date.today()-dt.timedelta(days=(volAvgDays+days2look))), str(dt.date.today()))
    
    if(startDate>=len(dateData)): #if a stock returns nothing or very few data pts
      return validBuy
    
    while(float(dateData[startDate][1])/float(dateData[startDate+1][1])<firstJumpAmt and startDate<min(days2look,len(dateData)-2)):
      startDate += 1
      #we know the date of the initial jump (startDate)
      
      if(float(dateData[startDate][1])/float(dateData[startDate+1][1])>=firstJumpAmt):
        
        avgVol = sum([int(dateData[i][2]) for i in range(startDate,min(startDate+volAvgDays,len(dateData)))])/volAvgDays #avg of volumes over a few days
        
        lastVol = int(dateData[startDate][2]) #the latest volume
        lastPrice = float(dateData[startDate][4]) #the latest highest price

        if(lastVol/avgVol>volGain): #much larger than normal volume
          #volume had to have gained
          #if the next day's price has fallen significantly and the volume has also fallen
          if(float(dateData[startDate-days2wait4fall][4])/lastPrice-1<priceDrop and int(dateData[startDate-days2wait4fall][2])<=lastVol*volLoss):
            #the jump happened, the volume gained, the next day's price and volumes have fallen
            dayPrice = lastPrice
            i = 1 #increment through days looking for a jump - start with 1 day before startDate
            # check within the the last few days, check the price has risen compared to the past some days, and we're within the valid timeframe
            while(i<=checkPriceDays and lastPrice/dayPrice<checkPriceAmt and startDate+i<len(dateData)):
              dayPrice = float(dateData[startDate+i][4])
              i += 1
            
            if(lastPrice/dayPrice>=checkPriceAmt):
              #the price jumped compared to both the previous day and to the past few days, the volume gained, and the price and the volume both fell
              #check to see if we missed the next jump (where we want to strike)
              missedJump = False
              for e in range(0,startDate):
                diff = float(dateData[e][1])/float(dateData[e+1][1])
                if(diff>=sellUp):
	                  missedJump = True
              if(not missedJump):
                validBuy = dateData[startDate][0] #return the date the stock initially jumped
    
  return validBuy #return a dict of valid stocks and the date of their latest jump
  
  
#the new version of the getGainers function - uses the new functions getList, getHistory, and goodBuy
def getGainers(symblist): #default to the getList - otherwise use what the user provides
  gainers = {}
  
  for i,e in enumerate(symblist):
    b = goodBuy(e)
    if(b!="NA"):
      print(f"({i+1}/{len(symblist)}) {e}",end='')
      gainers[e] = [b,(dt.datetime.strptime(b,"%m/%d/%Y")+dt.timedelta(days=(7*5))).strftime("%m/%d/%Y")]
      print(" - "+gainers[e][0]+" - "+gainers[e][1])
  return gainers
